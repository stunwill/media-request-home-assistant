"""Bounded Prowlarr queries and transparent candidate processing, no acquisition."""
from __future__ import annotations

import asyncio
import hashlib
import re
from time import monotonic

import httpx
from fastapi import HTTPException

from . import main, release_identity as identity, release_search_control as control

MAX_PAGES = 3
PAGE_SIZE = 100
MAX_ROWS = 2400
SEARCH_SECONDS = 8
_capability_cache = {}


def terms(movie):
    variants = identity._movie_titles(movie)
    official = str(movie.get('title') or movie.get('original_title') or '').strip()
    # Prefer the grammatical alias, not whichever foreign alternative is shortest.
    originals = [str(movie.get(key) or '').strip() for key in ('title','original_title')]
    short = [value for value in variants if any(re.fullmatch(re.escape(value)+r'\s+or\s+\(.+\)',title,flags=re.I) for title in originals)]
    regional = [str(item.get('title') or '').strip() for item in movie.get('alternative_titles') or []
                if isinstance(item,dict) and item.get('iso_3166_1') in {'AU','US','GB'}]
    chosen = []
    for value in [*short,*originals,*regional,*variants]:
        if value and value.casefold() not in {item.casefold() for item in chosen}:
            chosen.append(value)
    if official and official not in chosen[:3]:
        chosen = chosen[:2]+[official]
    year = str(movie.get('year') or str(movie.get('release_date') or '')[:4])
    queries = []
    for title in chosen[:3]:
        title = ' '.join(re.sub(r'[()]',' ',title).split())
        if year.isdigit():
            queries.append(f'{title} {year}')
        queries.append(title)
    return list(dict.fromkeys(queries))


def categories(items):
    values = []
    for item in items or []:
        if isinstance(item,dict):
            values.append(item)
            values.extend(categories(item.get('subCategories') or item.get('subcategories') or []))
    return values


def movie_categories(indexers):
    return sorted({int(category['id']) for indexer in indexers for category in categories((indexer.get('capabilities') or {}).get('categories'))
                   if str(category.get('id') or '').isdigit() and
                   (2000<=int(category['id'])<3000 or str(category.get('name') or '').lower().startswith('movies'))})


def movie_category_rejected(item):
    known=categories(item.get('categories'))
    if not known:
        return False  # Identity, not missing category metadata, decides.
    if any(2000<=int(c.get('id') or 0)<3000 or str(c.get('name') or '').lower().startswith('movies') for c in known if str(c.get('id') or '0').isdigit()):
        return False
    return any(str(c.get('name') or '').lower().startswith(('tv','audio','books','xxx')) or
               3000<=int(c.get('id') or 0)<8000 for c in known if str(c.get('id') or '0').isdigit())


def release_key(item):
    indexer=str(item.get('indexerId') or item.get('indexer_id') or item.get('indexer') or '')
    identifier=item.get('guid') or item.get('infoHash') or item.get('downloadUrl')
    return (indexer,str(identifier)) if identifier else (indexer,str(item.get('title')),str(item.get('size')))


async def capabilities(client,url,key,trace):
    cache_key=(url,hashlib.sha256(key.encode()).hexdigest())
    cached=_capability_cache.get(cache_key)
    if cached and cached[0]>monotonic():
        trace['capabilities']='cached' if cached[1] else 'unavailable'
        return cached[1]
    try:
        async with asyncio.timeout(2):
            response=await client.get('/api/v1/indexer',params={})
            response.raise_for_status()
            payload=response.json()
        indexes=[{name:item.get(name) for name in ('id','enable','supportsSearch','supportsPagination','capabilities')}
                 for item in payload if isinstance(item,dict) and 'capabilities' in item and item.get('enable') and item.get('supportsSearch',True)] if isinstance(payload,list) else []
        if len(_capability_cache)>32:
            _capability_cache.clear()
        _capability_cache[cache_key]=(monotonic()+300,indexes)
        trace['capabilities']='available' if indexes else 'unavailable'
        return indexes
    except (httpx.HTTPError,ValueError,TimeoutError):
        trace['capabilities']='unavailable'
        return []


async def search(movie):
    options=await asyncio.to_thread(main.load_options)
    integrations=options.get('integrations',{})
    url=str(integrations.get('prowlarr_url') or '').rstrip('/')
    key=str(integrations.get('prowlarr_api_key') or '').strip()
    trace=control.discovery_diagnostics.get()
    if trace is None:
        trace={}
    trace.setdefault('timestamp',main.utc_now())
    trace.update({'queries':[],'raw_results':0,'duplicates_removed':0,'title_mismatches':0,
                  'category_exclusions':0,'metadata_exclusions':0,'failed_queries':0,'bounded':False,
                  'indexers_returned':0,'indexers_configured':None,'rows_not_processed':0})
    if not url or not key:
        trace['prowlarr_status']='not_configured'
        return []
    results=[];seen=set();indexer_ids=set();errors=[];successes=0
    semaphore=asyncio.Semaphore(4)
    async with httpx.AsyncClient(base_url=url,timeout=httpx.Timeout(6,connect=3,pool=3),
                                headers={'X-Api-Key':key,'User-Agent':'MediaHub/0.19.1'}) as client:
        indexes=await capabilities(client,url,key,trace)
        trace['indexers_configured']=len(indexes) if indexes else None
        cats=movie_categories(indexes) or [2000]  # Prowlarr's normalized parent, never a tracker-local ID.
        paginating=any(item.get('supportsPagination') for item in indexes) if indexes else True
        limits=[int((item.get('capabilities') or {}).get('limitsMax')) for item in indexes
                if str((item.get('capabilities') or {}).get('limitsMax') or '').isdigit() and int(item['capabilities']['limitsMax'])>0]
        page_size=min([PAGE_SIZE,*limits])
        queries=[params for term in terms(movie) for params in ({'query':term,'type':'movie','categories':cats},{'query':term})]
        for name,field in [('imdbid','imdb_id'),('tmdbid','tmdb_id')]:
            supported=[item['id'] for item in indexes if name in {str(value).lower() for value in (item.get('capabilities') or {}).get('movieSearchParams') or []}]
            value=movie.get(field)
            if supported and value and (name!='imdbid' or re.fullmatch(r'tt\d+',str(value))):
                queries.append({'query':'{'+name+':'+str(value)+'}','type':'movie','categories':cats,'indexerIds':supported})
                break  # One supported identifier lookup, not redundant ID fan-out.
        async def query(params):
            nonlocal successes
            async with semaphore:
                entry={'query':params['query'],'scope':'movie_categories' if 'categories' in params else 'broad',
                       'category_ids':params.get('categories',[]),'pages':0,'raw':0,'outcome':'searching',
                       'requested_indexer_count':len(params.get('indexerIds') or indexes) if indexes else None}
                trace['queries'].append(entry)
                try:
                    async with asyncio.timeout(control.PROVIDER_SECONDS):
                        previous=None
                        for page in range(MAX_PAGES):
                            response=await client.get('/api/v1/search',params={**params,'limit':page_size,'offset':page*page_size})
                            response.raise_for_status();payload=response.json()
                            if not isinstance(payload,list):
                                raise ValueError('Invalid search response')
                            successes+=1;entry['pages']+=1;entry['raw']+=len(payload);trace['raw_results']+=len(payload)
                            signature=tuple(release_key(item) for item in payload if isinstance(item,dict))
                            prior_raw=trace['raw_results']-len(payload)
                            for position,item in enumerate(payload):
                                if prior_raw+position>=MAX_ROWS:
                                    trace['bounded']=True
                                    trace['rows_not_processed']+=len(payload)-position
                                    break
                                if not isinstance(item,dict):
                                    trace['metadata_exclusions']+=1;continue
                                if item.get('indexerId') is not None:
                                    indexer_ids.add(str(item['indexerId']))
                                marker=release_key(item)
                                if marker in seen:
                                    trace['duplicates_removed']+=1;continue
                                seen.add(marker)
                                if movie_category_rejected(item):
                                    trace['category_exclusions']+=1;continue
                                if not identity.validate_movie_release(movie,item).eligible:
                                    trace['title_mismatches']+=1;continue
                                results.append(item)
                            if len(payload)<page_size:
                                break
                            if not paginating or signature==previous or page==MAX_PAGES-1 or trace['raw_results']>=MAX_ROWS:
                                trace['bounded']=True;break
                            previous=signature
                    entry['outcome']='success'
                except (httpx.HTTPError,ValueError,TimeoutError,TypeError,OverflowError) as error:
                    errors.append(error);trace['failed_queries']+=1
                    entry['outcome']='timeout' if isinstance(error,(TimeoutError,httpx.TimeoutException)) else 'provider_error'
                except asyncio.CancelledError:
                    entry['outcome']='cancelled';raise
        tasks=[asyncio.create_task(query(params)) for params in queries]
        try:
            _,pending=await asyncio.wait(tasks,timeout=SEARCH_SECONDS)
            if pending:
                trace['bounded']=True
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
    trace['indexers_returned']=len(indexer_ids)
    trace['queries_not_started']=len(queries)-len(trace['queries'])
    trace['prowlarr_status']='partial' if errors or trace['bounded'] else 'success'
    if any(isinstance(error,httpx.HTTPStatusError) and error.response.status_code in {401,403} for error in errors):
        raise HTTPException(503,'Prowlarr credentials were rejected. Check Setup.')
    if not successes:
        if trace['bounded'] or errors and all(isinstance(error,(TimeoutError,httpx.TimeoutException)) for error in errors):
            raise control.timeout_error()
        if errors:
            raise HTTPException(502,'Prowlarr search failed. Check Setup.')
    return results
