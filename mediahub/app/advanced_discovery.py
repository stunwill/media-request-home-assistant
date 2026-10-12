"""TMDb candidate discovery plus transparent, indexed multi-source enrichment."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from datetime import date, timedelta

from fastapi import HTTPException, Request

from . import critic_ratings, main, media_services, ratings_providers as providers, ratings_store as store, tv_main, tv_services

SORTS = {'tmdb':'vote_average.desc','popular':'popularity.desc','reviewed':'vote_count.desc',
         'newest':'primary_release_date.desc','oldest':'primary_release_date.asc','added':None,
         'imdb':None,'rt_critic':None,'rt_audience':None,'metacritic':None,'letterboxd':None,'trakt':None}


def criteria(params):
    try:
        rules = json.loads(params.get('ratings','{}'))
        if not isinstance(rules,dict) or len(rules)>len(providers.SOURCES):
            raise ValueError()
        result = {}
        for source,rule in rules.items():
            if source not in providers.SOURCES or not isinstance(rule,dict):
                raise ValueError()
            normal = {}
            for name in ('min','max','votes'):
                value = rule.get(name)
                if value is None or value == '':
                    continue
                parsed = float(value)
                maximum = 1e9 if name == 'votes' else providers.SOURCES[source]
                if not math.isfinite(parsed) or parsed<0 or parsed>maximum or name=='votes' and not parsed.is_integer():
                    raise ValueError()
                normal[name] = parsed
            if normal.get('min',0)>normal.get('max',providers.SOURCES[source]):
                raise ValueError()
            if normal:
                result[source] = normal
        if params.get('rt_min') is not None or params.get('rt_max') is not None:
            rule = result.setdefault('rt_critic',{})
            for field,param in [('min','rt_min'),('max','rt_max')]:
                if params.get(param) is not None:
                    value=float(params[param])
                    if not math.isfinite(value) or not 0<=value<=100:
                        raise ValueError()
                    rule[field]=value
            if rule.get('min',0)>rule.get('max',100):
                raise ValueError()
        return result
    except (ValueError, TypeError):
        raise HTTPException(422,'Invalid rating range. Use each source\'s scale and minimum no greater than maximum.')


def option_number(params,name,maximum=2100):
    raw=params.get(name)
    if raw in (None,''):
        return None
    try:
        value=int(raw)
        if not 0<=value<=maximum:
            raise ValueError()
        return value
    except ValueError:
        raise HTTPException(422,f'Invalid {name}.')


def validate(params):
    rules=criteria(params)
    if params.get('sort','popular') not in SORTS:
        raise HTTPException(422,'Unsupported sort option.')
    for lo,hi in [('year_from','year_to'),('runtime_min','runtime_max')]:
        low,high=option_number(params,lo),option_number(params,hi)
        if low is not None and high is not None and low>high:
            raise HTTPException(422,f'{lo} must not exceed {hi}.')
    if params.get('missing','exclude') not in {'exclude','include'}:
        raise HTTPException(422,'Missing-score policy must be include or exclude.')
    if params.get('query') and any(params.get(name) for name in ('language','country','runtime_min','runtime_max','streaming_au')):
        raise HTTPException(422,'Language, country, runtime and streaming filters require discovery without a text search. TMDb search does not support these constraints.')
    return rules


def scope_for(kind,params):
    base=critic_ratings.scope_key(kind,params.get('query',''),params.get('collection','popular'))
    constraints={name:params.getlist(name) for name in ('genre_id','year_from','year_to','language','country','runtime_min','runtime_max','streaming_au') if params.get(name)}
    return hashlib.sha256((base+json.dumps(constraints,sort_keys=True)).encode()).hexdigest()


async def candidates(kind,params,page):
    query=params.get('query','').strip()
    collection=params.get('collection','popular')
    allowed = {'popular','top_rated','now_playing','upcoming'} if kind=='movie' else {'popular','top_rated','airing_today','on_the_air'}
    if collection not in allowed:
        raise HTTPException(422,'Unknown discovery category.')
    client = main.configured_clients(main.load_options())[0] if kind=='movie' else tv_main.tv_clients()[0]
    if query:
        # Keep actor search and current Movie/TV search behaviour.
        data = await client.catalogue(query=query,page=page,collection=collection)
        return data
    prefix='movie' if kind=='movie' else 'tv'
    sort=params.get('sort','popular')
    options={'page':page,'include_adult':'false','sort_by':SORTS.get(sort) or 'popularity.desc'}
    if kind=='tv':
        options['sort_by']=options['sort_by'].replace('primary_release_date','first_air_date')
    genres=params.getlist('genre_id')
    if genres:
        if any(not value.isdigit() for value in genres):
            raise HTTPException(422,'Invalid genre selection.')
        options['with_genres']=','.join(genres)
    for source,target in [('language','with_original_language'),('country','with_origin_country'),
                           ('runtime_min','with_runtime.gte'),('runtime_max','with_runtime.lte')]:
        if params.get(source):
            options[target]=params[source]
    rules=criteria(params)
    tmdb=rules.get('tmdb',{})
    for source,target in [('min','vote_average.gte'),('max','vote_average.lte'),('votes','vote_count.gte')]:
        if source in tmdb:
            options[target]=tmdb[source]
    for source,target in [('rating_from','vote_average.gte'),('rating_to','vote_average.lte')]:
        if params.get(source):
            options[target]=params[source]
    date_field='primary_release_date' if kind=='movie' else 'first_air_date'
    if params.get('year_from'):
        options[date_field+'.gte']=f"{int(params['year_from']):04d}-01-01"
    if params.get('year_to'):
        options[date_field+'.lte']=f"{int(params['year_to']):04d}-12-31"
    today=date.today()
    if kind=='movie' and collection in {'now_playing','upcoming'}:
        lower=today-timedelta(days=60) if collection=='now_playing' else today+timedelta(days=1)
        upper=today if collection=='now_playing' else today+timedelta(days=365)
        options[date_field+'.gte']=max(options.get(date_field+'.gte',lower.isoformat()),lower.isoformat())
        options[date_field+'.lte']=min(options.get(date_field+'.lte',upper.isoformat()),upper.isoformat())
    if collection=='top_rated':
        options.setdefault('vote_count.gte',250 if kind=='movie' else 50)
    if kind=='tv' and collection in {'airing_today','on_the_air'}:
        options['air_date.gte']=today.isoformat()
        options['air_date.lte']=(today if collection=='airing_today' else today+timedelta(days=7)).isoformat()
    if params.get('streaming_au')=='true':
        options['watch_region']='AU'
        options['with_watch_monetization_types']='flatrate'
    payload=await client._get(f'/discover/{prefix}',options)
    normalise=media_services.normalise_movie if kind=='movie' else tv_services.normalise_tv_show
    return {'movies' if kind=='movie' else 'shows':[normalise(item) for item in payload.get('results') or []],
            'page':payload.get('page',page),'total_pages':min(500,payload.get('total_pages',1)),
            'total_results':payload.get('total_results',0)}


def filter_local(kind,scope,params,page,rules):
    with main.connect_db() as db:
        rows=db.execute('''SELECT c.payload,t.first_seen FROM critic_catalogue c
          LEFT JOIN rating_titles t ON t.kind=c.media_type AND t.tmdb_id=c.tmdb_id
          WHERE c.scope=? AND c.media_type=? ORDER BY c.tmdb_id''',(scope,kind)).fetchall()
    data=[{**json.loads(row['payload']),'first_seen':row['first_seen'] or 0} for row in rows]
    scores=store.snapshot(kind,[item['tmdb_id'] for item in data])
    coverage={'inspected':len(data),'verified':0,'awaiting':0,'unavailable':0,'expired':0,'failed':0,'outside_range':0,
              'missing_excluded':0,'sources':{source:0 for source in rules}}
    matches=[]
    for item in data:
        matrix=scores[str(item['tmdb_id'])]
        item['ratings_data']=matrix
        missing=False
        rejected=False
        states=[]
        for source,rule in rules.items():
            entry=matrix[source]
            if entry['status']=='verified' and entry.get('value') is not None:
                coverage['sources'][source]+=1
            states.append(entry['status'])
            if entry['status']!='verified' or entry.get('value') is None:
                missing=True
                continue
            if entry['value']<rule.get('min',0) or entry['value']>rule.get('max',providers.SOURCES[source]):
                rejected=True
            if 'votes' in rule:
                if entry.get('votes') is None:
                    missing=True
                    states[-1]='not_retrieved'
                elif entry['votes']<rule['votes']:
                    rejected=True
        if any(state=='not_retrieved' for state in states):
            coverage['awaiting']+=1
        elif any(state=='expired' for state in states):
            coverage['expired']+=1
        elif any(state not in {'verified','unavailable'} for state in states):
            coverage['failed']+=1
        elif any(state=='unavailable' for state in states):
            coverage['unavailable']+=1
        else:
            coverage['verified']+=1
        if rejected:
            coverage['outside_range']+=1
        if missing and params.get('missing','exclude')!='include':
            coverage['missing_excluded']+=1
        if rejected or missing and params.get('missing','exclude')!='include':
            continue
        year=int(item.get('year') or 0)
        rating=float(item.get('rating') or 0)
        if params.get('year_from') and year<int(params['year_from']) or params.get('year_to') and year>int(params['year_to']):
            continue
        if params.get('rating_from') and rating<float(params['rating_from']) or params.get('rating_to') and rating>float(params['rating_to']):
            continue
        if params.getlist('genre_id') and not set(map(int,params.getlist('genre_id'))).issubset(set(item.get('genre_ids') or [])):
            continue
        item['ratings_incomplete']=missing
        matches.append(item)
    sort=params.get('sort','popular')
    def ordering(item):
        if sort in providers.SOURCES:
            entry=item['ratings_data'][sort]
            value=entry.get('value') if entry['status']=='verified' else None
            return (value is None,-(value or 0),item['tmdb_id'])
        if sort in {'oldest','newest'}:
            raw=item.get('release_date') or item.get('first_air_date')
            try:
                value=date.fromisoformat(raw).toordinal() if raw else date(int(item.get('year') or 1),1,1).toordinal()
            except (ValueError,TypeError):
                value=0
            return (not value,value if sort=='oldest' else -value,item['tmdb_id'])
        value=item.get('first_seen') if sort=='added' else item.get('vote_count') if sort=='reviewed' else item.get('year') if sort in {'oldest','newest'} else item.get('popularity')
        try:
            value=float(value or 0)
        except ValueError:
            value=0
        return (False,value if sort=='oldest' else -value,item['tmdb_id'])
    matches.sort(key=ordering)
    incomplete=coverage['awaiting']+coverage['failed']+coverage['expired']
    message=f"{len(matches)} {'results (unverified titles labelled)' if params.get('missing')=='include' else 'verified-data matches'} in {len(data)} inspected TMDb candidates. "
    if incomplete or coverage['unavailable']:
        message+=f"{coverage['awaiting']} awaiting, {coverage['expired']} expired, {coverage['failed']} failed, {coverage['unavailable']} unavailable. "
    message+='This is an incremental candidate dataset, not the whole catalogue. Enrich this discovery to inspect more candidates.'
    if not any(store.key(provider) for provider in store.EXTERNAL) and any(source!='tmdb' for source in rules):
        message='External ratings are not configured. Add MDBList or OMDb in Setup, or choose TMDb filters. '+message
    result_state = ('enrichment_required' if not data else 'partial' if matches and (incomplete or coverage['unavailable']) else
                    'results' if matches else 'provider_error' if coverage['failed'] else
                    'enrichment_required' if coverage['awaiting'] or coverage['expired'] else
                    'ratings_unavailable' if coverage['unavailable'] else 'no_matches')
    headings={'enrichment_required':'Enrichment required, not proof of no matching titles.',
              'provider_error':'Provider error: some ratings could not be evaluated.',
              'ratings_unavailable':'Ratings unavailable for the inspected candidates.',
              'partial':'Partial results: ratings coverage is incomplete.', 'no_matches':'No matching titles in the verified inspected dataset.'}
    if result_state in headings:
        message=headings[result_state]+' '+message
    message+=' '+'. '.join(f'{source.replace("_"," ")}: verified scores for {count} of {len(data)} inspected titles' for source,count in coverage['sources'].items())
    return {'movies' if kind=='movie' else 'shows':matches[(page-1)*20:page*20],
            'page':page,'total_results':len(matches),'total_pages':max(1,math.ceil(len(matches)/20)),
            'coverage':coverage,'catalogue_notice':message,'search_scope':'incremental_tmdb_candidates',
            'result_state':result_state}


async def discover(kind,request: Request,principal: main.CurrentUser):
    if kind not in {'movies','tv'}:
        raise HTTPException(404,'Unknown media type.')
    kind='movie' if kind=='movies' else 'tv'
    params=request.query_params
    rules=validate(params)
    available=store.availability(kind)['sources']
    disabled=[source for source in rules if not available[source]['enabled']]
    if params.get('sort') in available and not available[params['sort']]['enabled']:
        disabled.append(params['sort'])
    if disabled:
        raise HTTPException(422,'Ratings unavailable: '+', '.join(disabled)+'. Configure the supported provider in Setup or remove these filters.')
    page=option_number(params,'page',500) or 1
    scope=scope_for(kind,params)
    with main.connect_db() as db:
        count=db.execute('SELECT COUNT(*) n FROM critic_catalogue WHERE scope=? AND media_type=?',(scope,kind)).fetchone()['n']
    local=any(source!='tmdb' for source in rules) or params.get('sort') in set(providers.SOURCES)-{'tmdb'} or params.get('sort')=='added' or bool(params.get('query') and (rules or params.get('year_from') or params.get('genre_id')))
    try:
        if not local or not count:
            result=await candidates(kind,params,1 if local else page)
            items=result.get('movies' if kind=='movie' else 'shows') or []
            await asyncio.to_thread(critic_ratings.remember_catalogue,scope,kind,items)
            await asyncio.to_thread(store.ingest,kind,items)
            if not local:
                matrix=store.snapshot(kind,[item['tmdb_id'] for item in items])
                for item in items:
                    item['ratings_data']=matrix[str(item['tmdb_id'])]
                return result
        return await asyncio.to_thread(filter_local,kind,scope,params,page,rules)
    except main.MediaServiceError as error:
        raise main.service_http_error(error) from error


async def enrich(kind,request: Request,principal: main.CurrentUser):
    if kind not in {'movies','tv'}:
        raise HTTPException(404,'Unknown media type.')
    media='movie' if kind=='movies' else 'tv'
    params=request.query_params
    validate(params)
    scope=scope_for(media,params)
    with main.connect_db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS discovery_progress(scope TEXT PRIMARY KEY,next_page INTEGER NOT NULL)')
        row=db.execute('SELECT next_page FROM discovery_progress WHERE scope=?',(scope,)).fetchone()
        first=row['next_page'] if row else 1
    inspected=0
    last=first
    try:
        async with asyncio.timeout(18):
            for page in range(first,min(first+3,501)):
                result=await candidates(media,params,page)
                items=result.get('movies' if media=='movie' else 'shows') or []
                await asyncio.to_thread(critic_ratings.remember_catalogue,scope,media,items)
                await asyncio.to_thread(store.ingest,media,items)
                inspected+=len(items)
                last=page+1
                if page>=result.get('total_pages',1):
                    break
    except TimeoutError:
        pass
    with main.connect_db() as db:
        db.execute('INSERT OR REPLACE INTO discovery_progress VALUES(?,?)',(scope,last))
    return {'inspected':inspected,'next_candidate_page':last,'message':'Candidate inspection complete. Ratings are queued for background enrichment; refresh results as coverage increases.'}
