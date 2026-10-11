import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from mediahub.app import watchlist_main, critic_ratings as ratings, download_history as history, feature_release as feature, main, settings


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DATABASE_FILE', tmp_path/'mediahub.db')
    main.initialise_database()
    from mediahub.app import tv_release_selection
    tv_release_selection.initialise_tv_release_database()
    history.initialise()
    ratings.initialise()
    monkeypatch.setattr(main, 'load_options', lambda: {'integrations':{'omdb_api_key':'secret-test'}})
    return tmp_path


@pytest.mark.parametrize('value,expected', [('87%',87),('0%',0),('100%',100),('101%',None),('N/A',None),('8/10',None),('-1%',None)])
def test_only_verified_critic_score(value, expected):
    payload={'imdbID':'tt123','Type':'movie','Ratings':[{'Source':'Rotten Tomatoes','Value':value}]}
    assert ratings.extract_score(payload,'tt123','movie') == expected
    assert ratings.extract_score(payload,'tt124','movie') is None
    assert ratings.extract_score(payload,'tt123','tv') is None
    payload['Ratings'][0]['Source']='Audience score'
    assert ratings.extract_score(payload,'tt123','movie') is None


def test_provider_cache_missing_score_and_failures(database, monkeypatch):
    payload={'Response':'True','imdbID':'tt123','Type':'movie','Ratings':[{'Source':'Rotten Tomatoes','Value':'87%'}]}
    fetch=AsyncMock(return_value=payload)
    monkeypatch.setattr(ratings,'fetch_omdb',fetch)
    assert run(ratings.score_for('tt123','movie')) == 87
    assert run(ratings.score_for('tt123','movie')) == 87
    assert fetch.await_count == 1
    fetch.return_value={'Response':'True','imdbID':'tt124','Type':'series','Ratings':[]}
    assert run(ratings.score_for('tt124','tv')) is None
    assert run(ratings.score_for('tt124','tv')) is None
    assert fetch.await_count == 2
    fetch.side_effect=httpx.ConnectError('secret provider URL')
    assert run(ratings.score_for('tt125','movie')) is None
    assert run(ratings.score_for('tt125','movie')) is None
    assert fetch.await_count == 3


def test_budget_shared_and_disabled_provider(database, monkeypatch):
    monkeypatch.setattr(ratings,'DAILY_BUDGET',2)
    assert ratings.reserve_request()
    assert ratings.reserve_request()
    assert not ratings.reserve_request()
    fetch=AsyncMock();monkeypatch.setattr(ratings,'fetch_omdb',fetch)
    assert run(ratings.score_for('tt123','movie')) is None
    assert not fetch.called
    monkeypatch.setattr(main,'load_options',lambda:{})
    assert run(ratings.score_for('tt123','movie')) is None


def test_secret_persistence_redaction_and_settings_api(database):
    target=database/'settings.json'
    settings.save_integration_settings({'omdb_api_key':'secret-test'},settings_file=target)
    assert target.stat().st_mode & 0o777 == 0o600
    assert 'secret-test' not in json.dumps(settings.public_integration_settings({'integrations':{'omdb_api_key':'secret-test'}}))
    record=logging.LogRecord('httpx',logging.INFO,'',1,'HTTP Request GET https://www.omdbapi.com/?apikey=secret-test',(),None)
    ratings._HideOmdbRequest().filter(record)
    assert 'secret-test' not in record.getMessage()
    from mediahub.app.plex_main import PlexIntegrationSettingsUpdate
    assert PlexIntegrationSettingsUpdate(updates={'omdb_api_key':'secret-test'}).updates['omdb_api_key']=='secret-test'


@pytest.mark.parametrize('kind',['movie','tv'])
def test_cached_catalogue_filters_all_cached_pages_and_unknowns(database,kind):
    scope=ratings.scope_key(kind,'','popular')
    for page in range(3):
        items=[{'tmdb_id':page*20+i,'title':f'Title {page*20+i}', 'year':'2020', 'rating':8,'genre_ids':[18]} for i in range(1,21)]
        ratings.remember_catalogue(scope,kind,items)
        for item in items:
            ratings.save_catalogue_score(kind,item['tmdb_id'],80)
    ratings.save_catalogue_score(kind,1,None)
    ratings.save_catalogue_score(kind,2,0)
    result=ratings.filtered_catalogue(scope,kind,1,70,100,[18],2010,2024,7,9)
    assert result['total_results']==58
    assert result['total_pages']==3
    key='movies' if kind=='movie' else 'shows'
    pages=[ratings.filtered_catalogue(scope,kind,page,70,100,[18],2010,2024,7,9)[key] for page in range(1,4)]
    assert len({item['tmdb_id'] for page in pages for item in page})==58
    assert result['rt_scope']=='cached_verified' and 'not the complete' in result['catalogue_notice']
    assert ratings.filtered_catalogue(scope,kind,1,None,0,[],None,None,None,None)['total_results']==1
    assert ratings.filtered_catalogue(scope,kind,1,80,None,[99],None,None,None,None)['total_results']==0
    with pytest.raises(HTTPException):
        ratings.filtered_catalogue(scope,kind,1,90,20,[],None,None,None,None)


def test_identity_cache_uses_authoritative_ids(database,monkeypatch):
    client=type('Client',(),{'_get':AsyncMock(return_value={'imdb_id':'tt123'})})()
    monkeypatch.setattr(main,'configured_clients',lambda options:(client,None,None))
    score=AsyncMock(return_value=87);monkeypatch.setattr(ratings,'score_for',score)
    assert run(feature.lookup_score('movie',123))==87
    assert run(feature.lookup_score('movie',123))==87
    assert client._get.await_count==1
    assert score.call_args.args==('tt123','movie')


def insert_request(status='queued',title='Movie',kind='movie'):
    with main.connect_db() as db:
        cursor=db.execute('''INSERT INTO requests(media_type,title,external_id,requested_by_id,requested_by_name,
          estimated_size_gb,reserved_size_gb,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          (kind,title,'1','stu','Stuart',1.5,0,status,'2026-10-01T00:00:00+00:00','2026-10-02T00:00:00+00:00'))
        return cursor.lastrowid


def test_additive_migration_preserves_history_unknown_times(database):
    request_id=insert_request('available')
    history.initialise();history.initialise()
    with main.connect_db() as db:
        item=history.history_item(db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone())
    assert item['requested_by_name']=='Stuart'
    assert item['display_timestamp'] is None
    assert item['size_is_estimate']
    assert item['display_progress'] is None
    assert item['created_at']=='2026-10-01T00:00:00+00:00'


def test_evidence_preserves_first_timestamps_transfer_is_not_available(database):
    request_id=insert_request('processing')
    with main.connect_db() as db:
        history.evidence(db,request_id,torrent={'total_size':123456789,'completion_on':1791761040,'progress':1})
        row=db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone()
        timestamp=row['download_completed_at']
        assert row['status']=='processing'
        history.evidence(db,request_id,torrent={'completion_on':1791762040},imported_at='2026-10-12T09:24:00+11:00')
    with main.connect_db() as db:
        item=history.history_item(db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone())
    assert item['download_completed_at']==timestamp
    assert item['actual_size_bytes']==123456789
    assert item['imported_at']=='2026-10-11T22:24:00+00:00'
    assert item['display_status']=='Importing'
    assert item['display_timestamp']==item['created_at']


def test_completed_transfer_zero_remaining_enters_importing():
    status,progress,_=main._download_status({'size':100,'sizeleft':0},None)
    assert status=='processing' and progress==100


def test_history_page_permissions_failures_and_tv_labels(database,monkeypatch):
    for i in range(55):
        insert_request(title=f'Movie {i}')
    selected=insert_request('failed','Original TV torrent','tv')
    with main.connect_db() as db:
        db.execute('UPDATE requests SET series_title=?,season_number=2,episode_number=3,rejection_reason=? WHERE id=?',('Series','Actual failure',selected))
    monkeypatch.setattr(history,'refresh',AsyncMock(return_value='Integration unavailable'))
    principal=main.Principal('stu','stu','Stuart','requester',True)
    result=run(history.history(principal,page=1,page_size=50))
    second=run(history.history(principal,page=2,page_size=50))
    assert result['total']==56 and result['total_pages']==2
    assert len({item['id'] for item in result['items']+second['items']})==56
    tv=next(item for item in result['items'] if item['id']==selected)
    assert tv['display_title']=='Series · S02E03'
    assert tv['rejection_reason']=='Actual failure'
    assert result['warning']=='Integration unavailable'
    assert run(history.history(main.Principal('other','other','Other','requester',True),page=1,page_size=50))['total']==0


def test_discovery_cache_settings_owner_refresh_and_concurrency(database):
    async def scenario():
        feature._release_cache.clear();feature._release_locks.clear()
        op=AsyncMock(return_value={'releases':[{'eligible':True}]})
        result=await asyncio.gather(feature.cached_discovery(('a',),op,False),feature.cached_discovery(('a',),op,False))
        assert result[0]==result[1] and op.await_count==1
        await feature.cached_discovery(('a',),op,True)
        assert op.await_count==2
        await feature.cached_discovery(('b',),op,False)
        assert op.await_count==3
        assert not feature._release_locks
    run(scenario())


def test_rt_api_validation_provider_status_and_no_credentials(database):
    app=watchlist_main.app
    principal=main.Principal('stu','stu','Stuart','admin',True)
    app.dependency_overrides[main.current_user]=lambda:principal
    try:
        with TestClient(app) as client:
            assert client.get('/api/catalog/movies?rt_min=101').status_code==422
            assert client.get('/api/catalog/tv?rt_min=90&rt_max=10').status_code==422
            response=client.get('/api/setup/omdb')
            assert response.status_code==200 and response.json()['configured']
            assert 'secret-test' not in response.text
            assert client.post('/api/critic-ratings',json={'media_type':'tv','ids':list(range(21))}).status_code==422
    finally:
        app.dependency_overrides.clear()


def test_discovery_registers_unmonitored_arr_metadata_only(database):
    from types import SimpleNamespace
    from mediahub.app import media_services, tv_services, release_search_control as control
    async def scenario():
        movie=media_services.RadarrClient('http://radarr.test','key')
        movie.movies=AsyncMock(return_value=[])
        movie._defaults=AsyncMock(return_value=SimpleNamespace(quality_profile_id=1,root_folder_path='/media'))
        movie._request=AsyncMock(side_effect=[{'tmdbId':1},{'id':4}])
        token=control.discovery_only.set(True)
        try:
            await movie.ensure_movie(1)
        finally:
            control.discovery_only.reset(token)
        body=movie._request.call_args.kwargs['json']
        assert body['monitored'] is False
        assert body['addOptions']=={'searchForMovie':False}
        show=tv_services.SonarrClient('http://sonarr.test','key')
        show.series=AsyncMock(return_value=[])
        show.lookup=AsyncMock(return_value=[{'tvdbId':2,'seasons':[{'seasonNumber':1}]}])
        show.defaults=AsyncMock(return_value=SimpleNamespace(quality_profile_id=1,root_folder_path='/media'))
        show._request=AsyncMock(return_value={'id':8})
        token=control.discovery_only.set(True)
        try:
            await show.ensure_series({'tmdb_id':1,'external_ids':{'tvdb_id':2}})
        finally:
            control.discovery_only.reset(token)
        body=show._request.call_args.kwargs['json']
        assert body['monitored'] is False
        assert not any(season['monitored'] for season in body['seasons'])
        assert body['addOptions']['searchForMissingEpisodes'] is False
    run(scenario())


def test_handoff_invalidates_user_tokens_cache(database):
    feature._release_cache={('movie',1,'stu','settings',()):(1,{}),('movie',1,'lee','settings',()):(1,{})}
    feature.invalidate_user_releases('stu')
    assert all(key[2]=='lee' for key in feature._release_cache)
    feature._release_cache.clear()
