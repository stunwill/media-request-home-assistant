import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import QueryParams

from mediahub.app import watchlist_main, main, tv_main, tv_release_selection, download_history, download_management as management, ratings_store as store, advanced_discovery as discovery, enhanced_main  # noqa: F401


@pytest.fixture
def database(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DATABASE_FILE',tmp_path/'db.sqlite')
    monkeypatch.setattr(main,'load_options',lambda:{})
    main.initialise_database();tv_main.initialise_tv_database();tv_release_selection.initialise_tv_release_database()
    download_history.initialise();management.initialise();store.initialise()
    return tmp_path


def principal(role='admin',user='stu'):
    return main.Principal(user,user,user,role,True)


def insert(identity='1',kind='movie',status='failed',user='stu',scope=None,season=None,episode=None):
    with main.connect_db() as db:
        cursor=db.execute('''INSERT INTO requests(media_type,title,external_id,requested_by_id,requested_by_name,
         estimated_size_gb,reserved_size_gb,status,created_at,updated_at,requested_scope,season_number,episode_number)
         VALUES(?,?,?,?,?,1,0,?,'2026-10-12T01:00:00+00:00','2026-10-12T01:00:00+00:00',?,?,?)''',
         (kind,'Identical long title',identity,user,user,status,scope,season,episode))
        return cursor.lastrowid


def query(**kwargs):
    return management.query_groups(principal(),kwargs.get('page',1),kwargs.get('page_size',30),kwargs.get('sort','newest'),kwargs.get('media','all'),kwargs.get('requester',''),kwargs.get('status','all'))


def test_group_identity_latest_attempt_and_history(database):
    first=insert();latest=insert(status='queued');insert(identity='2')
    result=query();assert result['total']==2
    group=next(item for item in result['items'] if item['external_id']=='1')
    assert group['id']==latest and group['attempt_count']==2
    attempts=asyncio.run(management.attempts(latest,principal(),page=1))
    assert [row['id'] for row in attempts['items']]==[latest,first]
    assert attempts['items'][1]['status']=='failed'
    with main.connect_db() as db:assert db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]==3


def test_tv_scopes_and_legacy_empty_identity_not_grouped(database):
    insert(kind='tv',scope='episode',season=2,episode=3);insert(kind='tv',scope='episode',season=2,episode=4)
    insert(kind='tv',scope='season_pack',season=2);insert(identity='');insert(identity='')
    assert query()['total']==5


def test_pagination_filters_sort_latest_and_permissions(database):
    for identity in range(45):insert(str(identity),user='lee' if identity%2 else 'stu')
    assert len(query(page_size=20)['items'])==20
    assert query(page=3,page_size=20)['total_pages']==3
    assert query(sort='oldest')['items'][0]['id']==1
    assert query(requester='lee')['total']==22
    limited=management.query_groups(principal('requester'),1,30,'newest','all','','all')
    assert limited['total']==23 and {u['id'] for u in limited['requesters']}=={'stu'}
    other=insert('other',user='lee')
    with pytest.raises(HTTPException) as error:asyncio.run(management.attempts(other,principal('requester'),page=1))
    assert error.value.status_code==404
    insert('0',status='available')
    assert query(status='failed')['total']==45  # Identity 0 now available, plus "other".


def test_additive_migration_repeated_preserves_history(database):
    request_id=insert()
    for _ in range(3):main.initialise_database();management.initialise()
    with main.connect_db() as db:
        row=dict(db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone())
    assert row['created_at']=='2026-10-12T01:00:00+00:00' and row['sent_at'] is None
    assert row['failure_json'] is None and row['status']=='failed'


def test_failure_redaction_and_unknown_lifecycle(database):
    request_id=insert()
    with main.connect_db() as db:
        db.execute('UPDATE requests SET status_message=? WHERE id=?',('Radarr rejected https://indexer.test/?apikey=SECRET token=SECRET',request_id))
    item=query()['items'][0]
    assert 'SECRET' not in json.dumps(item)
    assert item['failure']['integration']=='Radarr' and 'timestamp' not in item['failure']
    assert item['lifecycle']['client']=='Not confirmed' and item['retry_supported']
    assert item['display_progress'] is None


@pytest.mark.parametrize('state',['pausedDL','stoppedDL','queuedDL','checkingDL','metaDL'])
def test_paused_or_waiting_client_not_downloading(state):
    assert main._download_status({}, {'state':state,'progress':0,'dlspeed':0})[0]=='queued'
    assert main._download_status({}, {'state':state,'progress':0.8,'dlspeed':0})[0]=='queued'


def test_complete_transfer_is_not_available_and_sent_not_downloading():
    assert main._download_status({}, {'state':'uploading','progress':1})[0]=='processing'
    assert main._download_status({'status':'queued'},None)[0]=='queued'


def test_unknown_client_progress_and_paused_start_not_fabricated(database):
    request_id=insert(status='queued')
    with main.connect_db() as db:
        download_history.evidence(db,request_id,torrent={'state':'pausedDL','size':100,'dlspeed':0},queue={'status':'downloading'})
        row=dict(db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone())
    assert row['download_started_at'] is None and row['progress_known']==0


def test_failure_not_rewritten_when_another_attempt_imports(database,monkeypatch):
    failed=insert();active=insert(status='queued')
    movie={'id':4,'tmdbId':1,'hasFile':True,'movieFile':{'dateAdded':'2026-10-12T02:00:00Z'}}
    monkeypatch.setattr(main,'configured_clients',lambda options:(None,type('R',(),{'queue':AsyncMock(return_value=[]),'movies':AsyncMock(return_value=[movie])})(),type('Q',(),{'torrents':AsyncMock(return_value=[])})()))
    asyncio.run(enhanced_main.downloads(principal()))
    with main.connect_db() as db:
        assert db.execute('SELECT status FROM requests WHERE id=?',(failed,)).fetchone()[0]=='failed'
        assert db.execute('SELECT status FROM requests WHERE id=?',(active,)).fetchone()[0]=='available'


def test_ratings_capabilities_omdb_not_audience_and_cache(database,monkeypatch):
    monkeypatch.setattr(main,'load_options',lambda:{'integrations':{'omdb_api_key':'fixture'}})
    available=store.availability()['sources']
    assert available['imdb']['enabled'] and not available['rt_audience']['enabled']
    assert available['tmdb']['enabled']
    with main.connect_db() as db:
        db.execute("INSERT INTO rating_values VALUES('movie',1,'mdblist','rt_audience',90,NULL,'verified',?,?,NULL)",(time.time(),time.time()+100))
    assert store.availability()['sources']['rt_audience']['enabled']
    assert store.availability()['sources']['rt_audience']['verified_cached']==1


def test_unconfigured_source_rejected_before_candidate_request(database,monkeypatch):
    candidates=AsyncMock();monkeypatch.setattr(discovery,'candidates',candidates)
    request=type('Request',(),{'query_params':QueryParams({'ratings':json.dumps({'rt_audience':{'min':80}})})})()
    with pytest.raises(HTTPException) as error:asyncio.run(discovery.discover('movies',request,principal()))
    assert error.value.status_code==422 and 'Ratings unavailable' in error.value.detail
    assert not candidates.called


def test_public_availability_no_secrets_and_users_authorization(database):
    app=main.app;app.dependency_overrides[main.current_user]=lambda:principal('requester')
    try:
        with TestClient(app) as client:
            assert client.get('/api/ratings/availability').status_code==200
            assert client.post('/api/users',json={'display_name':'Lee','username':'lee','password':'longpassword123','role':'admin'}).status_code==403
            assert client.get('/api/users').status_code==403
    finally:app.dependency_overrides.clear()


def test_audit_backfill_is_verified_and_idempotent(database):
    request_id=insert()
    with main.connect_db() as db:
        main.record_audit(db,actor_id='system',actor_name='MediaHub',action='movie_release_grabbed',request_id=request_id,
                          details={'release':{'quality':'1080p','indexer':'Recorded source'}})
        stamp=db.execute('SELECT occurred_at FROM audit_events').fetchone()[0]
    management.initialise();management.initialise()
    item=query()['items'][0]
    assert item['sent_at']==stamp and item['selected_release_quality']=='1080p'
    assert item['selected_release_source']=='Recorded source' and item['download_completed_at'] is None


@pytest.mark.parametrize('state,outcome',[('verified','no_matches'),('not_retrieved','enrichment_required'),('unavailable','ratings_unavailable'),('expired','enrichment_required'),('unavailable_provider','provider_error')])
def test_result_states_and_verified_source_coverage(database,state,outcome):
    from mediahub.app import critic_ratings
    critic_ratings.initialise();scope='scope'
    critic_ratings.remember_catalogue(scope,'movie',[{'tmdb_id':1,'title':'Example','year':'2020','rating':8}])
    if state!='not_retrieved':
        with main.connect_db() as db:
            db.execute("INSERT INTO rating_values VALUES('movie',1,'mdblist','rt_audience',50,NULL,?,?,?,NULL)",
                       ('verified' if state=='expired' else state,time.time(),time.time()-1 if state=='expired' else time.time()+100))
    result=discovery.filter_local('movie',scope,QueryParams({}),1,{'rt_audience':{'min':80}})
    assert result['result_state']==outcome
    assert result['coverage']['sources']['rt_audience']==(1 if state=='verified' else 0)
    assert result['coverage']['missing_excluded']==(0 if state=='verified' else 1)


def test_included_unrated_titles_not_claimed_verified_matches(database):
    from mediahub.app import critic_ratings
    critic_ratings.initialise();critic_ratings.remember_catalogue('scope','movie',[{'tmdb_id':1,'title':'Example','rating':8}])
    result=discovery.filter_local('movie','scope',QueryParams({'missing':'include'}),1,{'rt_audience':{'min':80}})
    assert result['total_results']==1 and result['movies'][0]['ratings_incomplete']
    assert 'verified-data matches' not in result['catalogue_notice']
