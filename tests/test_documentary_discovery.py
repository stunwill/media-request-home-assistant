"""Sanitised user observations, not claims of live tracker access."""
import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mediahub.app import watchlist_main, main, runtime, release_identity as identity  # noqa: F401
from mediahub.app import prowlarr_discovery as discovery, release_search_control as control
from mediahub.app import release_activity, release_lifecycle, feature_release
from test_birdman_discovery import run_search, CAPS

DOCUMENTARY = {'id':5070,'name':'TV/Documentary'}
MOVIES = [({'title':'Daniel','year':'2023','genres':[{'id':99,'name':'Documentary'}]},1.32,2),
          ({'title':'Beyond Utopia','year':'2023','genres':[{'id':99,'name':'Documentary'}]},2.13,5)]


def row(movie, size, seeders, **changes):
    return {'title':f"{movie['title']} (2023) 1080p WEBRip 5 1-LAMA",'size':int(size*1024**3),
            'seeders':seeders,'indexerId':7,'indexer':'Fixture Movies','guid':'fixture-doc',
            'categories':[DOCUMENTARY],'downloadUrl':'https://fixture.invalid/private?passkey=SECRET',**changes}


@pytest.mark.parametrize('movie,size,seeders',MOVIES)
def test_documentaries_survive_discovery_identity_and_policy(movie,size,seeders):
    raw=row(movie,size,seeders)
    def handler(request):
        if request.url.path.endswith('/indexer'):
            return httpx.Response(200,json=[{**CAPS[0],'capabilities':{'categories':[DOCUMENTARY]}}])
        return httpx.Response(200,json=[raw])
    results,trace=run_search(handler,movie)
    assert len(results)==1
    assert DOCUMENTARY['id'] in trace['queries'][0]['category_ids']
    assert identity.validate_movie_release(movie,results[0]).eligible
    public=runtime._prowlarr_policy(runtime._normalise_prowlarr_release(results[0],radarr_indexer_id=21),main.ReleaseRules())
    assert public['eligible'] and public['seeders']==seeders


@pytest.mark.parametrize('title',['Daniel Howell Were All Doomed (2024) WEB 720p WEBRip-LAMA',
    'Daniel Howell Were All Doomed (2023) 1080p','Daniel (2022) 1080p','Daniel Extra Words 1080p'])
def test_daniel_shared_word_is_not_identity(title):
    assert not identity.validate_movie_release(MOVIES[0][0],{'title':title}).eligible


def test_duplicate_unknown_observation_does_not_hide_eligible_metadata():
    movie,size,seeds=MOVIES[0];raw=row(movie,size,seeds,categories=[{'id':2000,'name':'Movies'}])
    def handler(request):
        if request.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
        return httpx.Response(200,json=[{**raw,'seeders':None,'size':None},raw])
    results,trace=run_search(handler,movie)
    assert len(results)==1 and results[0]['seeders']==2 and results[0]['size']==raw['size']


@pytest.mark.parametrize('value,expected',[(0,0),('0',0),(None,None),('',None),('N/A',None),(-1,None),('2',2),(' 5 ',5),(2.1,None),(True,None)])
def test_seeders_are_known_nonnegative_integers(value,expected):
    assert identity.seeder_count(value)==expected
    normalized=runtime._normalise_prowlarr_release({**row(*MOVIES[0]),'seeders':value},radarr_indexer_id=21)
    assert normalized['seeders']==expected
    assert runtime._prowlarr_policy(normalized,main.ReleaseRules())['eligible']==bool(expected and expected>=1)


def test_indexer_local_documentary_id_is_discovered_by_name():
    movie,size,seeds=MOVIES[1];custom={'id':100073,'name':'Documentaries'}
    caps=[{**CAPS[0],'capabilities':{'categories':[custom]}}]
    def handler(request):
        if request.url.path.endswith('/indexer'):return httpx.Response(200,json=caps)
        # Exercise source-specific name lookup when the row only provides an ID.
        return httpx.Response(200,json=[row(movie,size,seeds,categories=[{'id':100073}])])
    results,trace=run_search(handler,movie)
    assert len(results)==1 and trace['queries'][0]['category_ids']==[100073]
    assert discovery.movie_categories(CAPS,MOVIES[0][0])==[2000,2040,2050]


@pytest.mark.parametrize('movie', [MOVIES[0][0], {'title':'Daniel','year':'2023'}])
def test_tv_episodes_never_become_documentary_movies(movie):
    assert not identity.validate_movie_release(movie,{'title':'Daniel S01E01 2023 1080p'}).eligible
    assert discovery.movie_category_rejected({'categories':[{'id':5000,'name':'TV'}]},movie)


def test_category_fallback_uses_broad_query_and_preserves_strict_identity():
    movie,size,seeds=MOVIES[0]
    def handler(request):
        if request.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
        return httpx.Response(200,json=[] if 'categories' in request.url.params else
                              [row(movie,size,seeds),row(movie,size,seeds,guid='wrong',title='Daniel Extra 2023 1080p')])
    results,trace=run_search(handler,movie)
    assert len(results)==1 and trace['title_mismatches']==1
    assert any(entry['scope']=='broad' for entry in trace['queries'])


def test_transient_retry_is_bounded_and_429_is_not_retried():
    attempts={}
    def handler(request):
        if request.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
        key=str(request.url);attempts[key]=attempts.get(key,0)+1
        if 'categories' in request.url.params and attempts[key]==1:return httpx.Response(503)
        return httpx.Response(200,json=[row(*MOVIES[0])])
    results,trace=run_search(handler,MOVIES[0][0])
    assert results and trace['retries']==2 and not trace['failed_queries']
    assert max(attempts.values())==2
    results,trace=run_search(lambda request:httpx.Response(200,json=CAPS) if request.url.path.endswith('/indexer') else
                            httpx.Response(429) if 'categories' in request.url.params else httpx.Response(200,json=[]),MOVIES[0][0])
    assert trace['failed_queries'] and trace['retries']==0 and trace['prowlarr_status']=='partial'


def test_budget_records_not_started_and_cancelled_paths_without_orphans():
    async def scenario():
        movie={**MOVIES[0][0],'alternative_titles':[{'title':'Verified Alias'},{'title':'Another Alias'}]}
        original=httpx.AsyncClient;trace={};token=control.discovery_diagnostics.set(trace)
        entered=0;active=0;peak=0
        async def handler(request):
            nonlocal entered,active,peak
            if request.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
            entered+=1;active+=1;peak=max(peak,active)
            try:
                await asyncio.sleep(.2)
                return httpx.Response(200,json=[])
            finally:active-=1
        discovery._capability_cache.clear()
        with patch.object(main,'load_options',return_value={'integrations':{'prowlarr_url':'https://fixture.test','prowlarr_api_key':'SECRET'}}), \
             patch.object(httpx,'AsyncClient',side_effect=lambda **opts:original(transport=httpx.MockTransport(handler),**opts)), \
             patch.object(discovery,'SEARCH_SECONDS',.02):
            try:
                with pytest.raises(main.HTTPException) as error:await discovery.search(movie)
            finally:control.discovery_diagnostics.reset(token)
        assert error.value.status_code==504 and entered==4 and active==0 and peak==4
        assert trace['queries_not_started']>0
        assert any(entry['outcome']=='cancelled' for entry in trace['queries'])
        assert len([task for task in asyncio.all_tasks() if task is not asyncio.current_task()])==0
    asyncio.run(scenario())


def test_alternative_timeout_preserves_partial_documentary_results():
    movie,size,seeds=MOVIES[1];movie={**movie,'alternative_titles':[{'title':'Verified Alias'}]}
    def handler(request):
        if request.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
        if 'Alias' in request.url.params['query']:raise httpx.ReadTimeout('PRIVATE_URL SECRET')
        return httpx.Response(200,json=[row(movie,size,seeds)])
    results,trace=run_search(handler,movie)
    assert len(results)==1 and trace['prowlarr_status']=='partial'
    assert any(entry['outcome']=='timeout' for entry in trace['queries'])
    assert 'SECRET' not in str(trace) and 'fixture.invalid' not in str(trace)


@pytest.mark.parametrize('role',['admin','manager','requester'])
@pytest.mark.parametrize('partial',[False,True])
def test_status_and_diagnostics_are_enforced_on_server(role,partial):
    async def scenario():
        async def candidates(*args,**kwargs):
            trace=control.discovery_diagnostics.get()
            trace.update({'raw_results':3,'bounded':partial,'failed_queries':int(partial),'release_exclusions':[]})
            return {'releases':[]}
        with patch.object(release_lifecycle,'movie_details',AsyncMock(return_value={'lifecycle':{'state':'released_unknown'}})), \
             patch.object(release_activity,'movie_releases',candidates):
            return await release_lifecycle.release_search(123,main.ReleaseRules(),main.Principal('id','user','User',role,True))
    result=asyncio.run(scenario())
    assert ('discovery_diagnostics' in result)==(role=='admin')
    assert result['search_complete']==(not partial)
    assert result['search_status']==('partial' if partial else 'no_matching')
    assert ('Partial results' in result['search_message'])==partial
    if partial:assert 'No matching releases' not in result['search_message']


def test_partial_results_are_not_cached():
    async def scenario():
        operation=AsyncMock(return_value={'releases':[{'title':'fixture'}],'search_complete':False})
        key=('documentary-test',)
        await feature_release.cached_discovery(key,operation,False)
        await feature_release.cached_discovery(key,operation,False)
        assert operation.await_count==2 and key not in feature_release._release_cache
    asyncio.run(scenario())


def test_redacted_release_level_diagnostics_and_distinct_release_identifiers():
    movie,size,seeds=MOVIES[0]
    def handler(request):
        if request.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
        return httpx.Response(200,json=[row(movie,size,seeds),row(movie,size,seeds,guid='distinct'),
                                      row(movie,size,seeds,guid='secret',title='https://secret.invalid?passkey=SECRET',indexer='token=SECRET')])
    results,trace=run_search(handler,movie)
    assert len(results)==2
    assert len(trace['release_exclusions'])==3
    assert not any(word in str(trace) for word in ['SECRET','downloadUrl','fixture.invalid','secret.invalid','passkey'])


def test_conflicting_size_quality_observations_are_not_merged():
    movie,size,seeds=MOVIES[0]
    variants=[row(movie,size,seeds),row(movie,1.6,seeds),row(movie,5,seeds,title='Daniel (2023) 2160p WEB-LAMA')]
    def handler(request):
        return httpx.Response(200,json=CAPS if request.url.path.endswith('/indexer') else variants)
    results,_=run_search(handler,movie)
    assert len(results)==3
    assert sum(runtime._prowlarr_policy(runtime._normalise_prowlarr_release(raw,radarr_indexer_id=21),main.ReleaseRules())['eligible'] for raw in results)==2


@pytest.mark.parametrize('change',[{'seeders':0},{'seeders':None},{'title':'Daniel (2023) 2160p WEBRip-LAMA'},{'size':4*1024**3}])
def test_documentary_preset_rejections_remain_specific(change):
    public=runtime._prowlarr_policy(runtime._normalise_prowlarr_release({**row(*MOVIES[0]),**change},radarr_indexer_id=21),main.ReleaseRules())
    assert not public['eligible'] and public['policy_rejections']


def test_documentary_final_pipeline_never_ranks_wrong_daniel():
    async def scenario():
        movie,size,seeds=MOVIES[0];movie={**movie,'tmdb_id':123}
        def handler(request):
            if request.url.path.endswith('/indexer'):return httpx.Response(200,json=CAPS)
            return httpx.Response(200,json=[row(movie,size,seeds),row(movie,size,100,guid='wrong',title='Daniel Howell Were All Doomed (2024) WEB 720p WEBRip-LAMA')])
        original=httpx.AsyncClient;discovery._capability_cache.clear()
        radarr=type('R',(),{'_request':AsyncMock(return_value=[{'id':21,'name':'Fixture Movies'}])})()
        with patch.object(main,'load_options',return_value={'integrations':{'prowlarr_url':'https://fixture.test','prowlarr_api_key':'SECRET'}}), \
             patch.object(httpx,'AsyncClient',side_effect=lambda **opts:original(transport=httpx.MockTransport(handler),**opts)), \
             patch.object(runtime,'_original_search_movie_releases',AsyncMock(return_value=({'id':88},[],False))), \
             patch.object(main,'configured_clients',return_value=(None,radarr,None)):
            _,results,_=await identity_pipeline(movie)
        assert len(results)==1 and results[0]['eligible'] and results[0]['release_token']
        assert 'Howell' not in results[0]['title']
    from mediahub.app import release_identity_main
    async def identity_pipeline(movie):
        return await release_identity_main.search_movie_releases(123,main.ReleaseRules(),'fixture-user',movie=movie)
    asyncio.run(scenario())
