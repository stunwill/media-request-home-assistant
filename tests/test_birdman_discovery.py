import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mediahub.app import watchlist_main, main, runtime, release_identity, release_identity_main, release_search_control as control  # noqa: F401
from mediahub.app import prowlarr_discovery as discovery, release_lifecycle, release_activity

MOVIE={'tmdb_id':194662,'imdb_id':'tt2562232','title':'Birdman or (The Unexpected Virtue of Ignorance)',
       'original_title':'Birdman or (The Unexpected Virtue of Ignorance)','year':'2014','release_date':'2014-10-17'}
VALID=[{'title':title,'size':int(size*1024**3),'seeders':seeders,'guid':f'fixture-{i}','indexerId':7,'indexer':'Fixture Movies',
        'categories':[{'id':2000 if i<2 else 2050,'name':'Movies' if i<2 else 'Movies/BluRay'}],'downloadUrl':'https://fixture.invalid/torrent', 'protocol':'torrent'}
       for i,(title,size,seeders) in enumerate([('Birdman 2014 1080p BluRay x265',1.8,74),
       ('Birdman 2014 1080p BluRay x265-LAMA',1.8,13),('Birdman 2014 1080p BluRay DDP5.1 x265 10bit-LAMA',2.7,31)])]


@pytest.mark.parametrize('release',VALID)
def test_birdman_short_title_is_valid_with_exact_year(release):
    assert runtime._matches_movie(release['title'],MOVIE)
    assert release_identity.validate_movie_release(MOVIE,release).eligible


def test_birdman_three_candidates_survive_full_identity_and_preset_chain():
    async def scenario():
        radarr=type('R',(),{'_request':AsyncMock(return_value=[{'id':21,'name':'Fixture Movies'}])})()
        with patch.object(runtime,'_original_search_movie_releases',AsyncMock(return_value=({'id':88},[],False))), \
             patch.object(runtime,'_prowlarr_search',AsyncMock(return_value=VALID)), \
             patch.object(main,'configured_clients',return_value=(None,radarr,None)),patch.object(main,'load_options',return_value={}):
            _,releases,_=await release_identity_main.search_movie_releases(MOVIE['tmdb_id'],main.ReleaseRules(maximum_size_gb=3,minimum_seeders=1),'fixture-user',movie=MOVIE)
        assert len(releases)==3
        assert all(release['eligible'] and release.get('release_token') for release in releases)
        assert sorted(release['size_gb'] for release in releases)==pytest.approx([1.8,1.8,2.7])
    asyncio.run(scenario())


CAPS=[{'id':7,'enable':True,'supportsSearch':True,'supportsPagination':True,
       'capabilities':{'limitsMax':100,'movieSearchParams':['Q','ImdbId'],
                       'categories':[{'id':2000,'name':'Movies','subCategories':[{'id':2050,'name':'Movies/BluRay'},{'id':2040,'name':'Movies/HD'}]}]}}]


def run_search(handler,movie=MOVIE):
    async def scenario():
        trace={};token=control.discovery_diagnostics.set(trace)
        discovery._capability_cache.clear()
        original=httpx.AsyncClient
        with patch.object(main,'load_options',return_value={'integrations':{'prowlarr_url':'https://fixture.test','prowlarr_api_key':'SECRET'}}), \
             patch.object(httpx,'AsyncClient',side_effect=lambda **options:original(transport=httpx.MockTransport(handler),**options)):
            try:results=await runtime._prowlarr_search(movie)
            finally:control.discovery_diagnostics.reset(token)
        return results,trace
    return asyncio.run(scenario())


@pytest.mark.parametrize('title',['Birdman of Alcatraz 1962 1080p','Birdman of Alcatraz 2014 1080p',
    'Detective Conan S01E03 Birdman 2014 1080p','Dr Quinn S02E03 Birdman 2014 720p',
    'Birdman 2015 1080p','Birdman 1080p','Birdman 2014 Season 2 1080p'])
def test_short_alias_does_not_accept_unrelated_titles(title):
    assert not release_identity.validate_movie_release(MOVIE,{'title':title}).eligible
    assert not runtime._matches_movie(title,MOVIE)


def test_short_and_full_queries_actual_categories_identifier_and_dedup():
    requests=[]
    def handler(request):
        if request.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
        requests.append(dict(request.url.params))
        return httpx.Response(200,json=VALID)
    results,trace=run_search(handler)
    assert len(results)==3
    assert {'Birdman','Birdman 2014','Birdman or The Unexpected Virtue of Ignorance 2014'}<={item['query'] for item in requests}
    assert any(item['query']=='{imdbid:tt2562232}' and item['type']=='movie' for item in requests)
    assert trace['queries'][0]['category_ids']==[2000,2040,2050]
    assert trace['raw_results']==len(requests)*3 and trace['duplicates_removed']==trace['raw_results']-3
    assert trace['indexers_configured']==1 and trace['indexers_returned']==1
    assert 'SECRET' not in str(trace) and 'downloadUrl' not in str(trace)


def test_pagination_reaches_eligible_candidates_after_first_100():
    filler=[{**VALID[0],'guid':f'large-{i}','title':f'Birdman 2014 1080p oversized-{i}','size':8*1024**3} for i in range(100)]
    offsets=[]
    def handler(request):
        if request.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
        offset=int(request.url.params['offset']);offsets.append(offset)
        return httpx.Response(200,json=filler if offset==0 else VALID)
    results,trace=run_search(handler)
    assert {item['guid'] for item in VALID}<={item['guid'] for item in results}
    assert 100 in offsets and not trace['bounded']
    assert len(results)==103


def test_repeated_or_nonpaginating_pages_report_partial_not_loop():
    payload=[{**VALID[0],'guid':str(i)} for i in range(100)]
    def handler(request):
        return httpx.Response(200,json=CAPS if request.url.path.endswith('/indexer') else payload)
    results,trace=run_search(handler)
    assert len(results)==100 and trace['bounded']
    assert all(query['pages']==2 for query in trace['queries'])
    assert trace['duplicates_removed']>0


def test_response_not_silently_sliced_at_100_and_missing_metadata():
    payload=[{**VALID[0],'guid':str(i)} for i in range(120)]+[None,{**VALID[0],'guid':'bad-seeders','seeders':'N/A'}]
    def handler(request):return httpx.Response(200,json=[] if request.url.path.endswith('/indexer') else payload)
    results,trace=run_search(handler)
    assert len(results)==121 and trace['metadata_exclusions']==sum(item['pages'] for item in trace['queries'])
    public=runtime._prowlarr_policy(runtime._normalise_prowlarr_release(results[-1],radarr_indexer_id=21),main.ReleaseRules())
    assert not public['eligible'] and 'Seeder count is unavailable' in public['policy_rejections']


def test_partial_failure_empty_and_categories():
    unrelated={**VALID[0],'guid':'television','categories':[{'id':5000,'name':'TV'}]}
    def handler(request):
        if request.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
        if 'categories' in request.url.params:return httpx.Response(500)
        return httpx.Response(200,json=[*VALID,unrelated])
    results,trace=run_search(handler)
    assert len(results)==3 and trace['failed_queries'] and trace['prowlarr_status']=='partial'
    assert trace['category_exclusions']==1
    results,trace=run_search(lambda request:httpx.Response(200,json=[]))
    assert results==[] and trace['raw_results']==0


@pytest.mark.parametrize('change',[{'size':int(3.001*1024**3)},{'seeders':0},{'title':'Birdman 2014 2160p BluRay'},{'size':None},{'size':-1},{'guid':None}])
def test_household_and_missing_metadata_are_not_relaxed(change):
    normalized=runtime._normalise_prowlarr_release({**VALID[0],**change},radarr_indexer_id=21)
    public=runtime._prowlarr_policy(normalized,main.ReleaseRules(maximum_size_gb=3,minimum_seeders=1))
    assert not public['eligible'] and public['policy_rejections']


def test_alternative_metadata_titles_and_query_bound():
    movie={**MOVIE,'title':'Official Film','original_title':'Official Film','alternative_titles':[{'title':'Alternate Film'}]}
    assert release_identity.validate_movie_release(movie,{'title':'Alternate Film 2014 1080p'}).eligible
    assert 'Alternate Film 2014' in discovery.terms(movie)
    movie['alternative_titles']=[{'title':f'Alias {i}'} for i in range(100)]
    assert len(discovery.terms(movie))<=6 and 'Official Film 2014' in discovery.terms(movie)


def test_search_cancellation_drains_children():
    async def scenario():
        entered=asyncio.Event();cancelled=[]
        async def get(self,path,params=None):
            if path.endswith('/indexer'):return httpx.Response(200,json=CAPS,request=httpx.Request('GET','https://fixture.test'))
            entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.append(True)
        discovery._capability_cache.clear()
        with patch.object(main,'load_options',return_value={'integrations':{'prowlarr_url':'https://fixture.test','prowlarr_api_key':'key'}}),patch.object(httpx.AsyncClient,'get',get):
            task=asyncio.create_task(runtime._prowlarr_search(MOVIE));await entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
        assert len(cancelled)==4
    asyncio.run(scenario())


def test_capability_page_limits_and_unsupported_identifier():
    caps=[{**CAPS[0],'capabilities':{**CAPS[0]['capabilities'],'limitsMax':50,'movieSearchParams':['Q']}}]
    queries=[]
    def handler(request):
        if request.url.path.endswith('/indexer'):return httpx.Response(200,json=caps)
        queries.append(dict(request.url.params))
        return httpx.Response(200,json=[{**VALID[0],'guid':str(i)} for i in range(50)] if request.url.params['offset']=='0' else VALID)
    results,trace=run_search(handler)
    assert all(query['limit']=='50' for query in queries) and any(query['offset']=='50' for query in queries)
    assert not any(query['query'].startswith('{') for query in queries)
    assert len(results)==53 and not trace['bounded']


def test_known_conflicting_identifiers_rejected():
    assert not release_identity.validate_movie_release(MOVIE,{**VALID[0],'imdbId':12345}).eligible
    assert not release_identity.validate_movie_release(MOVIE,{**VALID[0],'tmdbId':12345}).eligible
    assert release_identity.validate_movie_release(MOVIE,{**VALID[0],'imdbId':2562232}).eligible


def test_missing_size_boundary_and_x265_tenbit_are_not_codec_rejections():
    for raw in VALID:
        public=runtime._prowlarr_policy(runtime._normalise_prowlarr_release(raw,radarr_indexer_id=21),main.ReleaseRules())
        assert public['eligible']
    assert runtime._prowlarr_policy(runtime._normalise_prowlarr_release({**VALID[0],'size':3*1024**3},radarr_indexer_id=21),main.ReleaseRules())['eligible']


def test_old_four_rejected_and_three_qualifying_end_to_end_diagnostics():
    async def scenario():
        blocked=[{'title':MOVIE['title']+' 2014 1080p '+str(i),'size_gb':8,'indexer':'Fixture Movies','quality':'1080p','eligible':False,
                  'policy_rejections':['Release exceeds the 3 GB movie limit']} for i in range(4)]
        radarr=type('R',(),{'_request':AsyncMock(return_value=[{'id':21,'name':'Fixture Movies'}])})()
        async def releases(*args,**kwargs):
            _,items,_=await release_identity_main.search_movie_releases(MOVIE['tmdb_id'],main.ReleaseRules(),'user',movie=MOVIE)
            return {'releases':items}
        with patch.object(release_lifecycle,'movie_details',AsyncMock(return_value={**MOVIE,'lifecycle':{'state':'released_unknown'}})), \
             patch.object(release_activity,'movie_releases',releases),patch.object(runtime,'_original_search_movie_releases',AsyncMock(return_value=({'id':88},blocked,False))), \
             patch.object(runtime,'_prowlarr_search',AsyncMock(return_value=VALID)),patch.object(main,'configured_clients',return_value=(None,radarr,None)),patch.object(main,'load_options',return_value={}):
            result=await release_lifecycle.release_search(MOVIE['tmdb_id'],main.ReleaseRules(),main.Principal('user','user','User','admin',True))
        assert len(result['releases'])==7 and result['discovery_diagnostics']['eligible_releases']==3
        assert result['discovery_diagnostics']['household_exclusions']==4
        assert result['search_state']=='results'
        assert control.discovery_diagnostics.get() is None
    asyncio.run(scenario())
