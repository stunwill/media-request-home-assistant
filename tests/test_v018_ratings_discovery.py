import asyncio
import json
import multiprocessing
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.datastructures import QueryParams

from mediahub.app import watchlist_main, main, ratings_providers as providers, ratings_store as store, advanced_discovery as discovery  # noqa: F401


def run(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture
def database(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DATABASE_FILE',tmp_path/'mediahub.db')
    monkeypatch.setattr(main,'load_options',lambda:{'integrations':{'mdblist_api_key':'dummy-mdb','omdb_api_key':'dummy-omdb'}})
    main.initialise_database()
    from mediahub.app import critic_ratings
    critic_ratings.initialise()
    store.initialise()
    return tmp_path


def test_omdb_sources_scales_votes_and_identity():
    data={'imdbID':'tt123','Type':'movie','imdbRating':'8.2','imdbVotes':'1,234','Metascore':'79',
          'Ratings':[{'Source':'Rotten Tomatoes','Value':'91%'}]}
    values=providers.normalise_omdb(data,'movie','tt123')
    assert values=={'imdb':(8.2,1234),'metacritic':(79,None),'rt_critic':(91,None)}
    assert 'rt_audience' not in values
    with pytest.raises(providers.ProviderFailure):
        providers.normalise_omdb(data,'tv','tt123')
    with pytest.raises(providers.ProviderFailure):
        providers.normalise_omdb(data,'movie','tt124')


def test_mdblist_native_scales_critic_audience_separate():
    data={'tmdb_id':123,'imdb_id':'tt123','type':'movie','ratings':[
        {'source':'tomatoes','value':91},{'source':'popcorn','value':87},
        {'source':'letterboxd','value':4.1},{'source':'trakt','value':8.3,'votes':1000}]}
    values=providers.normalise_mdblist(data,'movie',123,'tt123')
    assert values['rt_critic'][0]==91 and values['rt_audience'][0]==87
    assert values['letterboxd'][0]==4.1 and values['trakt'][1]==1000
    with pytest.raises(providers.ProviderFailure):
        providers.normalise_mdblist(data,'movie',124,'tt123')


@pytest.mark.parametrize('value',[None,'N/A','nan','inf',-1,101])
def test_invalid_or_missing_scores_never_zero(value):
    assert providers.number(value,100) is None
    assert providers.number(0,100)==0


def test_jobs_are_bounded_deduplicated_and_lease_reclaimed(database):
    store.ingest('movie',[{'tmdb_id':1,'title':'Movie','rating':8,'imdb_id':'tt123'}])
    assert store.enqueue('movie',[1,1])==0
    first=store.claim()
    assert first and first['state']=='pending'
    with main.connect_db() as db:
        db.execute('UPDATE rating_jobs SET lease_until=0 WHERE provider=?',(first['provider'],))
    assert store.claim()['provider']==first['provider']
    for _ in range(10):
        store.enqueue('movie',list(range(2,102)))
    with main.connect_db() as db:
        assert db.execute("SELECT COUNT(*) n FROM rating_jobs WHERE state IN ('pending','running')").fetchone()['n']<=400


def test_provider_failure_does_not_erase_cached_score(database,monkeypatch):
    store.ingest('movie',[{'tmdb_id':1,'title':'Movie','imdb_id':'tt123','rating':8}])
    monkeypatch.setattr(providers,'fetch',AsyncMock(return_value=({'tmdb_id':1,'imdb_id':'tt123','type':'movie','ratings':[{'source':'tomatoes','value':91}]},{})))
    job={'kind':'movie','tmdb_id':1,'provider':'mdblist','attempts':0}
    run(store.process(job))
    first=store.snapshot('movie',[1])['1']['rt_critic']
    monkeypatch.setattr(providers,'fetch',AsyncMock(side_effect=providers.ProviderFailure('temporarily_unavailable')))
    run(store.process(job))
    after=store.snapshot('movie',[1])['1']['rt_critic']
    assert first['value']==after['value']==91
    assert first['retrieved']==after['retrieved']
    assert after['error']=='temporarily_unavailable'
    assert store.health()['providers']['mdblist']['status']=='temporarily_unavailable'


def test_rate_limit_budget_and_provider_independence(database,monkeypatch):
    monkeypatch.setattr(store,'configuration',lambda:{'daily_budget':1,'cache_days':7,'background_enabled':True})
    store.reserve('mdblist')
    with pytest.raises(providers.ProviderFailure) as caught:
        store.reserve('mdblist')
    assert caught.value.status=='rate_limited'
    store.reserve('omdb')


def test_multisource_and_missing_votes_expiry_stable_pages(database):
    from mediahub.app import critic_ratings
    params=QueryParams({'ratings':json.dumps({'imdb':{'min':7.5,'votes':1000},'rt_critic':{'min':85},'metacritic':{'min':75}}),'sort':'imdb'})
    scope=discovery.scope_for('movie',params)
    items=[{'tmdb_id':i,'title':f'Movie {i}','rating':8,'year':'2024'} for i in range(1,45)]
    critic_ratings.remember_catalogue(scope,'movie',items)
    store.ingest('movie',items)
    with main.connect_db() as db:
        for i in range(1,44):
            for source,value,votes in [('imdb',8.2,1200),('rt_critic',91,None),('metacritic',79,None)]:
                db.execute('INSERT OR REPLACE INTO rating_values VALUES(?,?,?,?,?,?,?,?,?,?)',('movie',i,'mdblist',source,value,votes,'verified',time.time(),time.time()+3600,None))
    rules=discovery.criteria(params)
    pages=[discovery.filter_local('movie',scope,params,page,rules) for page in (1,2,3)]
    assert pages[0]['total_results']==43
    assert len({item['tmdb_id'] for page in pages for item in page['movies']})==43
    assert pages[0]['coverage']['awaiting']==1
    included=QueryParams(str(params)+'&missing=include')
    assert discovery.filter_local('movie',scope,included,1,rules)['total_results']==44
    with main.connect_db() as db:
        db.execute("UPDATE rating_values SET expires=0 WHERE tmdb_id=1 AND source='imdb'")
    assert discovery.filter_local('movie',scope,params,1,rules)['coverage']['expired']==1
    assert store.snapshot('movie',[1])['1']['imdb']['status']=='expired'


@pytest.mark.parametrize('rules',[{'imdb':{'min':11}},{'rt_critic':{'min':90,'max':80}},{'letterboxd':{'min':6}},{'imdb':{'votes':1.2}},{'rt_audience':{'min':'NaN'}}])
def test_filter_validation(rules):
    with pytest.raises(HTTPException):
        discovery.criteria(QueryParams({'ratings':json.dumps(rules)}))


def initialise_child(path,barrier):
    from mediahub.app import main,tv_main,tv_release_selection,download_history,watchlist_main,ratings_store
    main.DATABASE_FILE=Path(path)
    barrier.wait()
    main.initialise_database()
    tv_main.initialise_tv_database()
    tv_release_selection.initialise_tv_release_database()
    watchlist_main.initialise_watchlist_database()
    download_history.initialise()
    ratings_store.initialise()


@pytest.mark.parametrize('existing',[False,True])
def test_concurrent_process_startup_and_history_preservation(database,existing):
    path=main.DATABASE_FILE if existing else database/'fresh.db'
    if existing:
        with main.connect_db() as db:
            db.execute("INSERT INTO requests(media_type,title,external_id,requested_by_id,requested_by_name,estimated_size_gb,reserved_size_gb,status,created_at,updated_at) VALUES('movie','Preserved','1','stu','Stuart',1,0,'available','2020','2020')")
    context=multiprocessing.get_context('fork')
    barrier=context.Barrier(3)
    processes=[context.Process(target=initialise_child,args=(str(path),barrier)) for _ in range(3)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        if process.is_alive():
            process.terminate()
        assert process.exitcode==0
    if existing:
        main.initialise_database()
        with main.connect_db() as db:
            assert db.execute("SELECT title FROM requests WHERE external_id='1'").fetchone()['title']=='Preserved'
            assert len([row for row in db.execute('PRAGMA table_info(requests)') if row['name']=='download_started_at'])==1


def test_legacy_verified_ratings_migrated(database):
    with main.connect_db() as db:
        db.execute('INSERT INTO critic_identity VALUES(?,?,?,?)',('movie',123,'tt123',time.time()+3600))
        db.execute('INSERT INTO critic_cache VALUES(?,?,?,?,?)',('tt123','movie',91,time.time(),time.time()+3600))
    store.initialise()
    assert store.snapshot('movie',[123])['123']['rt_critic']['value']==91


def test_admin_diagnostics_are_read_only_and_redacted(database,monkeypatch):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from mediahub.app import ratings_api
    movie={'tmdb_id':123,'title':'Secret Mall Apartment','year':'2024'}
    tmdb=SimpleNamespace(details=AsyncMock(return_value=movie))
    radarr=SimpleNamespace(movies=AsyncMock(return_value=[]),releases=AsyncMock())
    monkeypatch.setattr(main,'configured_clients',lambda options:(tmdb,radarr,None))
    monkeypatch.setattr(ratings_api,'prowlarr_evidence',AsyncMock(return_value={'prowlarr_status':'search_completed','prowlarr_candidates':4,'possible_category_mismatch':True,'query_candidates':{'movie_category':0,'broad':4}}))
    app=watchlist_main.app
    app.dependency_overrides[main.current_user]=lambda:main.Principal('stu','stu','Stuart','requester',True)
    try:
        with TestClient(app) as client:
            assert client.get('/api/diagnostics/movies/123/releases').status_code==403
            app.dependency_overrides[main.current_user]=lambda:main.Principal('stu','stu','Stuart','admin',True)
            response=client.get('/api/diagnostics/movies/123/releases')
            assert response.status_code==200
            data=response.json()
            assert data['prowlarr_candidates']==4
            assert data['possible_category_mismatch']
            assert 'not proof' in data['category_evidence']
            assert 'dummy' not in response.text and 'http' not in response.text
            assert not radarr.releases.called
    finally:
        app.dependency_overrides.clear()


def test_background_worker_shutdown_returns_claimed_job(database,monkeypatch):
    entered=asyncio.Event()
    async def blocked(job):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(store,'process',blocked)
    async def scenario():
        store.ingest('movie',[{'tmdb_id':1,'title':'Movie','rating':8}])
        await store.start()
        await asyncio.wait_for(entered.wait(),2)
        await store.stop()
        assert not store._tasks
        with main.connect_db() as db:
            assert not db.execute("SELECT 1 FROM rating_jobs WHERE state='running'").fetchone()
    run(scenario())


def test_enrichment_checks_only_three_candidate_pages(database,monkeypatch):
    from types import SimpleNamespace
    request=SimpleNamespace(query_params=QueryParams('ratings=%7B%22rt_critic%22%3A%7B%22min%22%3A85%7D%7D'))
    fetch=AsyncMock(side_effect=[{'movies':[{'tmdb_id':i,'rating':8,'title':'Movie'}], 'total_pages':500} for i in range(1,4)])
    monkeypatch.setattr(discovery,'candidates',fetch)
    result=run(discovery.enrich('movies',request,None))
    assert result['inspected']==3 and fetch.await_count==3
    assert result['next_candidate_page']==4


def test_credential_repair_clears_auth_cooldown_not_good_scores(database):
    with main.connect_db() as db:
        db.execute("INSERT INTO rating_health VALUES('mdblist','authentication_failed',NULL,'authentication_failed',?,NULL)",(time.time()+3600,))
        db.execute("INSERT INTO rating_values VALUES('movie',1,'mdblist','imdb',8.2,1000,'verified',?,?,NULL)",(time.time(),time.time()+3600))
        db.execute("INSERT INTO rating_values VALUES('movie',2,'mdblist','imdb',NULL,NULL,'authentication_failed',?,?,'authentication_failed')",(time.time(),time.time()+3600))
    store.credentials_changed('mdblist')
    with main.connect_db() as db:
        assert db.execute("SELECT blocked_until FROM rating_health WHERE provider='mdblist'").fetchone()['blocked_until']==0
        assert db.execute('SELECT expires FROM rating_values WHERE tmdb_id=2').fetchone()['expires']==0
    assert store.snapshot('movie',[1])['1']['imdb']['value']==8.2
