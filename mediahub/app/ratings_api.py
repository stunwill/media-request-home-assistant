"""Authenticated discovery, cache state, configuration and read-only diagnostics."""
from __future__ import annotations

import asyncio
import json
import time

import httpx

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from . import advanced_discovery, enhanced_main, feature_release, main, ratings_providers as providers, ratings_store as store, runtime, settings

app=main.app
app.version='0.18.0'
app.add_event_handler('startup',store.start)
app.add_event_handler('shutdown',store.stop)


class Batch(BaseModel):
    media_type: str=Field(pattern='^(movie|tv)$')
    ids: list[int]=Field(max_length=20)


async def ratings(payload: Batch, _: main.CurrentUser):
    if any(value<=0 for value in payload.ids):
        raise HTTPException(422,'IDs must be positive.')
    await asyncio.to_thread(store.enqueue,payload.media_type,payload.ids)
    return {'ratings':await asyncio.to_thread(store.snapshot,payload.media_type,payload.ids),
            'configured':any(store.key(provider) for provider in store.EXTERNAL)}


class RatingConfiguration(BaseModel):
    cache_days: int=Field(7,ge=1,le=30)
    daily_budget: int=Field(400,ge=0,le=900)
    background_enabled: bool=True


async def configuration(payload: RatingConfiguration, _: main.Administrator):
    stored=settings._read_json(settings.SETTINGS_FILE)
    stored['ratings']=payload.model_dump()
    settings._atomic_write(stored,settings.SETTINGS_FILE)
    return store.configuration()


async def health(_: main.Administrator):
    return await asyncio.to_thread(store.health)


async def test_provider(provider: str, _: main.Administrator):
    if provider not in store.EXTERNAL:
        raise HTTPException(404,'Unknown provider.')
    if not store.key(provider):
        return {'status':'not_configured','message':'Save this provider key first.'}
    try:
        await asyncio.to_thread(store.reserve,provider)
        payload,_=await providers.fetch(provider,store.key(provider),'movie',278,'tt0111161')
        values=providers.normalise_omdb(payload,'movie','tt0111161') if provider=='omdb' else providers.normalise_mdblist(payload,'movie',278,'tt0111161')
        with main.connect_db() as db:
            db.execute('''INSERT INTO rating_health(provider,status,last_success,last_error,blocked_until)
              VALUES(?,'verified',?,NULL,0) ON CONFLICT(provider) DO UPDATE SET
              status='verified',last_success=excluded.last_success,last_error=NULL,blocked_until=0''',(provider,time.time()))
        return {'status':'connected','sources_returned':[source for source,(value,_) in values.items() if value is not None]}
    except providers.ProviderFailure as error:
        with main.connect_db() as db:
            db.execute('''INSERT INTO rating_health(provider,status,last_error,blocked_until)
              VALUES(?,?,?,?) ON CONFLICT(provider) DO UPDATE SET
              status=excluded.status,last_error=excluded.last_error,blocked_until=excluded.blocked_until''',
              (provider,error.status,error.status,time.time()+error.retry_after))
        return {'status':error.status,'message':'Provider test did not succeed. Check credentials, quota or provider availability.'}


async def diagnostics(tmdb_id: int, principal: main.Administrator):
    """Read-only, sanitized evidence. Does not ensure/add/grab a Movie."""
    tmdb,radarr,_=main.configured_clients(main.load_options())
    result={'timestamp':main.utc_now(),'tmdb_id':tmdb_id,'radarr_status':'not_checked',
            'radarr_candidates':0,'eligible':0,'rejected':0,'prowlarr_status':'not_checked',
            'prowlarr_candidates':0,'identity_rejected':None,'possible_category_mismatch':False}
    try:
        async with asyncio.timeout(18):
            movie=await tmdb.details(tmdb_id)
            result['identity']={'title':movie.get('title'),'year':movie.get('year'),'imdb_id':movie.get('imdb_id')}
            known=next((item for item in await radarr.movies() if int(item.get('tmdbId') or 0)==tmdb_id),None)
            releases=await radarr.releases(int(known['id'])) if known else []
            result['radarr_status']='connected' if known else 'movie_not_registered'
            result['radarr_candidates']=len(releases)
            result['radarr_policy_rejected']=sum(not item.get('approved',True) for item in releases)
            reasons={}
            from .preset_main import movie_rules
            rules=await asyncio.to_thread(movie_rules)
            for release in releases:
                evaluated=main.release_with_policy(release,rules)
                if evaluated['eligible']:
                    result['eligible']+=1
                else:
                    result['rejected']+=1
                    for reason in evaluated.get('policy_rejections') or []:
                        # Classify, never expose arbitrary indexer messages or URLs.
                        category='household_policy' if 'MediaHub' in reason or 'size' in reason.lower() or 'seeder' in reason.lower() else 'radarr_policy'
                        reasons[category]=reasons.get(category,0)+1
            result['rejection_reasons']=reasons
            if not releases:
                evidence=await prowlarr_evidence(movie)
                result.update(evidence)
                result['search_source']='prowlarr_read_only'
                # Existing fallback already performs Movie-category and broad
                # queries and strict matching. Its merged results cannot prove
                # which category query differed, so never claim a mismatch.
                result['category_evidence']='Counts compare Movie-category and broad queries. A possible mismatch is a diagnostic hint, not proof of indexer configuration.'
            else:
                result['search_source']='radarr'
    except TimeoutError:
        result['error']='search_timeout'
    except (main.MediaServiceError,HTTPException) as error:
        result['error']='provider_request_failed' if getattr(error,'status_code',None)!=504 else 'search_timeout'
    return result


async def prowlarr_evidence(movie):
    values=main.load_options().get('integrations',{})
    url=str(values.get('prowlarr_url') or '').rstrip('/')
    secret=str(values.get('prowlarr_api_key') or '')
    if not url or not secret:
        return {'prowlarr_status':'not_configured'}
    term=f"{movie.get('title','')} {movie.get('year','')}".strip()
    async with httpx.AsyncClient(base_url=url,timeout=4,headers={'X-Api-Key':secret}) as client:
        async def query(category):
            parameters={'query':term,'limit':100}
            if category:
                parameters.update({'type':'movie','categories':2000})
            response=await client.get('/api/v1/search',params=parameters)
            response.raise_for_status()
            payload=response.json()
            if not isinstance(payload,list):
                raise ValueError('invalid_response')
            return payload[:100]
        payloads=await asyncio.gather(query(True),query(False),return_exceptions=True)
    counts,matched={},{}
    rejected=0
    for name,payload in zip(('movie_category','broad'),payloads):
        if isinstance(payload,Exception):
            counts[name]=None
            matched[name]=None
            continue
        counts[name]=len(payload)
        matching=sum(runtime._matches_movie(item.get('title'),movie) for item in payload if isinstance(item,dict))
        matched[name]=matching
        rejected+=len(payload)-matching
    return {'prowlarr_status':'search_completed' if all(value is not None for value in counts.values()) else 'provider_request_failed',
            'query_candidates':counts,'query_identity_matches':matched,
            'prowlarr_candidates':sum(value or 0 for value in counts.values()),'identity_rejected':rejected,
            'possible_category_mismatch':matched.get('movie_category')==0 and bool(matched.get('broad'))}


app.add_api_route('/api/ratings',ratings,methods=['POST'])
app.add_api_route('/api/ratings/health',health,methods=['GET'])
app.add_api_route('/api/ratings/configuration',configuration,methods=['PUT'])
app.add_api_route('/api/ratings/providers/{provider}/test',test_provider,methods=['POST'])
app.add_api_route('/api/diagnostics/movies/{tmdb_id}/releases',diagnostics,methods=['GET'])
app.add_api_route('/api/discovery/{kind}',advanced_discovery.discover,methods=['GET'])
app.add_api_route('/api/discovery/{kind}/enrich',advanced_discovery.enrich,methods=['POST'])


async def compatible_critic_batch(payload: Batch, principal: main.CurrentUser):
    response=await ratings(payload,principal)
    return {'configured':response['configured'],'scores':{
        identifier:matrix['rt_critic']['value'] if matrix['rt_critic']['status']=='verified' else None
        for identifier,matrix in response['ratings'].items()}}


async def compatible_omdb_test(principal: main.Administrator):
    response=await test_provider('omdb',principal)
    response.setdefault('message','OMDb connected.' if response['status']=='connected' else 'OMDb test did not succeed.')
    return response


# Compatibility endpoints share the new cache/budget. No second enrichment
# implementation or independent request budget is active in the deployed app.
enhanced_main._replace_route('/api/critic-ratings','POST',compatible_critic_batch)
enhanced_main._replace_route('/api/setup/omdb/test','POST',compatible_omdb_test)

from .ratings_ui import UI  # noqa: E402
main.INDEX_HTML=main.INDEX_HTML.replace('</body>',UI+'\n</body>')
