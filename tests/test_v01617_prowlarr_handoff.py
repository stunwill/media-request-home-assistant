"""Exercise the deployed route and real Radarr HTTP client with a cached selection."""
import asyncio
import copy
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from mediahub.app import main, enhanced_main, movie_release_endpoint as endpoint, preset_main, runtime, watchlist_main
from mediahub.app.media_services import RadarrClient

MOVIE = {'tmdb_id': 653574, 'title': 'The Donut King', 'original_title': 'The Donut King',
         'year': '2020', 'release_date': '2020-10-30'}
RAW = {'guid': 'ipt-donut-guid', 'indexerId': 7, 'indexer': 'IPTorrents',
       'title': 'The Donut King 2020 1080p WEBRip x265', 'size': int(1.53 * 1024**3),
       'seeders': 9, 'infoHash': 'ABCDEF123', 'protocol': 'torrent',
       'downloadUrl': 'http://prowlarr.test/7/download?apikey=private-test-secret',
       'publishDate': '2026-10-07T01:00:00Z'}
USER = SimpleNamespace(user_id='household-user', display_name='Household', role='admin')


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DATABASE_FILE', tmp_path / 'mediahub.db')
    main.initialise_database()
    enhanced_main._cleanup_historical_active_duplicates()
    watchlist_main.initialise_watchlist_database()
    presets = copy.deepcopy(preset_main.DEFAULT_PRESETS)
    monkeypatch.setattr(preset_main, 'load_presets', lambda: presets)
    monkeypatch.setattr(main, 'load_options', lambda: {'storage': {
        'media_path': str(tmp_path), 'minimum_free_gb': 0, 'safety_margin_gb': 0,
        'reservation_multiplier': 1.5}})
    tmdb = SimpleNamespace(details=AsyncMock(return_value=MOVIE))
    state = SimpleNamespace(mode='success', pushed=False, calls=[], mapping=[{'id': 21, 'name': 'IPTorrents'}])

    async def transport(request):
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        state.calls.append((request.method, path, body))
        if path == '/api/v3/movie':
            result = [{'id': 88, 'tmdbId': MOVIE['tmdb_id'], 'hasFile': state.mode == 'available'}]
        elif path == '/api/v3/queue':
            result = {'records': [{'movieId': 88}] if state.mode == 'queued' else []}
        elif path == '/api/v3/indexer':
            result = state.mapping
        elif path == '/api/v3/release' and request.method == 'GET':
            if state.mode != 'radarr':
                pytest.fail('Direct Prowlarr selection must never require Radarr rediscovery')
            result = [{**RAW, 'indexerId': 21, 'approved': True, 'downloadAllowed': True,
                       'quality': {'quality': {'name': 'WEBDL-1080p'}}}]
        elif path == '/api/v3/release' and request.method == 'POST':
            assert state.mode == 'radarr'
            result = {'infoHash': RAW['infoHash']}
        elif path == '/api/v3/release/push':
            state.pushed = True
            if state.mode in {'timeout', 'cancel', 'disconnect'}:
                state.entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    state.cancelled.set()
            if state.mode == 'failure':
                return httpx.Response(502, json={'message': 'Rejected'})
            if state.mode == 'http_timeout':
                raise httpx.ReadTimeout('secret URL must not leak', request=request)
            result = [{'mappedMovieId': 88, 'approved': state.mode != 'reject', 'rejected': state.mode == 'reject'}]
        elif path == '/api/v3/history/movie':
            result = [{'id': 123, 'movieId': 88, 'eventType': 'grabbed', 'downloadId': RAW['infoHash'],
                       'data': {'guid': 'PUSH-' + RAW['downloadUrl']}}] if state.pushed and state.mode != 'unconfirmed' else []
        else:
            pytest.fail(f'Unexpected Radarr operation {request.method} {path}')
        return httpx.Response(200, json=result)

    radarr = RadarrClient('http://radarr.test', 'private-radarr-key', transport=httpx.MockTransport(transport))
    monkeypatch.setattr(main, 'configured_clients', lambda _: (tmdb, radarr, None))
    monkeypatch.setattr(runtime, '_prowlarr_search', AsyncMock(return_value=[RAW]))
    monkeypatch.setattr(runtime, '_original_search_movie_releases', AsyncMock(return_value=({'id': 88}, [], False)))
    original_overrides = dict(watchlist_main.app.dependency_overrides)
    watchlist_main.app.dependency_overrides[main.current_user] = lambda: USER
    main.release_cache.clear()
    yield state, presets, tmdb
    watchlist_main.app.dependency_overrides.clear()
    watchlist_main.app.dependency_overrides.update(original_overrides)
    main.release_cache.clear()


async def discover():
    _, releases, _ = await runtime.search_movie_releases(MOVIE['tmdb_id'], preset_main.movie_rules(), USER.user_id, movie=MOVIE)
    assert releases[0]['eligible']
    assert 'download_url' not in releases[0] and 'magnet_url' not in releases[0]
    return releases[0]['release_token']


async def download(token, tmdb_id=MOVIE['tmdb_id']):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=watchlist_main.app), base_url='http://ingress.test') as client:
        return await client.post(f'/api/movies/{tmdb_id}/request', json={
            'release_token': token, 'maximum_size_gb': 99, 'minimum_seeders': 0})


def records():
    with main.connect_db() as db:
        return [dict(row) for row in db.execute('SELECT * FROM requests')], [dict(row) for row in db.execute('SELECT * FROM audit_events')]


def test_effective_request_route_and_capture_graph():
    route = next(r for r in watchlist_main.app.routes if r.path == '/api/movies/{tmdb_id}/request')
    assert route.endpoint is endpoint.request_movie and route.dependant.call is endpoint.request_movie
    assert preset_main._original_request_movie is runtime.request_movie
    assert runtime._original_request_movie is enhanced_main.request_movie
    assert watchlist_main.app.version == '0.16.17'


def test_donut_discovery_to_exact_radarr_push_and_shared_lifecycle(setup):
    state, _, _ = setup
    async def scenario():
        token = await discover()
        cached = main.release_cache[token][3]
        assert cached['guid'] == RAW['guid'] and cached['indexer_id'] == 21 and cached['prowlarr_indexer_id'] == 7
        response = await download(token)
        assert response.status_code == 200, response.text
        assert response.json()['request']['status'] == 'queued'
        assert token not in main.release_cache
    asyncio.run(scenario())
    pushes = [body for method, path, body in state.calls if method == 'POST' and path == '/api/v3/release/push']
    assert len(pushes) == 1
    assert pushes[0] == {'guid': RAW['guid'], 'indexerId': 21, 'title': RAW['title'], 'size': RAW['size'],
                         'seeders': 9, 'infoHash': RAW['infoHash'], 'downloadUrl': RAW['downloadUrl'],
                         'magnetUrl': '', 'publishDate': RAW['publishDate'], 'protocol': 'torrent', 'tmdbId': MOVIE['tmdb_id']}
    rows, audits = records()
    assert len(rows) == 1 and rows[0]['selected_release_guid'] == RAW['guid']
    assert rows[0]['selected_release_title'] == RAW['title'] and rows[0]['download_id'] == RAW['infoHash']
    assert rows[0]['reserved_size_gb'] == round(1.53 * 1.5, 2)
    assert [a['action'] for a in audits] == ['movie_request_created', 'movie_release_grabbed']
    assert 'private-test-secret' not in json.dumps(audits)


@pytest.mark.parametrize('invalid', ['expired', 'wrong_user', 'wrong_movie', 'missing'])
def test_invalid_selection_rejected_before_external_work(setup, invalid):
    state, _, tmdb = setup
    token = main.cache_release(MOVIE['tmdb_id'], 'other-user' if invalid == 'wrong_user' else USER.user_id,
                               runtime._normalise_prowlarr_release(RAW, radarr_indexer_id=21))
    if invalid == 'expired':
        cached = main.release_cache[token]
        main.release_cache[token] = (0, *cached[1:])
    if invalid == 'missing':
        main.release_cache.pop(token)
    response = asyncio.run(download(token, 123 if invalid == 'wrong_movie' else MOVIE['tmdb_id']))
    assert response.status_code == 409 and 'expired' in response.text
    assert not state.calls and not tmdb.details.await_count and records() == ([], [])
    if invalid in {'wrong_user', 'wrong_movie'}:
        assert token in main.release_cache


@pytest.mark.parametrize('change', ['size', 'seeders', 'quality', 'mapping_missing', 'mapping_changed', 'wrong_identity', 'missing_link'])
def test_revalidate_selection_and_current_household_rules(setup, change):
    state, presets, _ = setup
    async def scenario():
        token = await discover()
        if change == 'size': presets['movies']['maximum_size_gb'] = 1
        if change == 'seeders': presets['movies']['minimum_seeders'] = 10
        if change == 'quality': presets['movies']['allowed_resolutions'] = ['720p']
        if change == 'mapping_missing': state.mapping = []
        if change == 'mapping_changed': state.mapping = [{'id': 21, 'name': 'Other tracker'}]
        if change == 'wrong_identity': main.release_cache[token][3]['title'] = 'Other Movie 2020 1080p'
        if change == 'missing_link': main.release_cache[token][3]['download_url'] = ''
        response = await download(token)
        assert response.status_code == (422 if change in {'size', 'seeders', 'quality'} else 409), response.text
        assert 'no longer available' not in response.text
    asyncio.run(scenario())
    assert not state.pushed and records() == ([], [])


@pytest.mark.parametrize('mode,code', [('failure', 502), ('reject', 422), ('unconfirmed', 502), ('http_timeout', 504)])
def test_radarr_failure_is_meaningful_and_releases_reservation(setup, mode, code):
    state, _, _ = setup
    state.mode = mode
    async def scenario():
        response = await download(await discover())
        assert response.status_code == code, response.text
        assert 'no longer available' not in response.text and 'private-test-secret' not in response.text
    asyncio.run(scenario())
    rows, audits = records()
    assert rows[0]['status'] == 'failed' and rows[0]['reserved_size_gb'] == 0
    assert [a['action'] for a in audits] == ['movie_request_created', 'movie_request_submission_failed']


@pytest.mark.parametrize('stop', ['timeout', 'cancel', 'disconnect', 'outer_deadline'])
def test_bounded_grab_cancellation_and_event_loop_responsiveness(setup, monkeypatch, stop):
    state, _, _ = setup
    state.mode = stop if stop != 'outer_deadline' else 'timeout'
    async def scenario():
        state.entered, state.cancelled = asyncio.Event(), asyncio.Event()
        token = await discover()
        disconnected = False
        request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=lambda: disconnected))
        monkeypatch.setattr(runtime, 'GRAB_SECONDS', .04 if stop == 'timeout' else 10)
        if stop == 'outer_deadline': monkeypatch.setattr(runtime, 'HANDOFF_SECONDS', .08)
        task = asyncio.create_task(endpoint.request_movie(MOVIE['tmdb_id'], main.MovieRequestCreate(release_token=token), USER, request))
        await asyncio.wait_for(state.entered.wait(), 1)
        # A concurrent ingress request can still be serviced while grab is pending.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=watchlist_main.app), base_url='http://ingress.test') as client:
            health = await asyncio.wait_for(client.get('/api/health'), .2)
            assert health.status_code == 200
        if stop == 'cancel': task.cancel()
        if stop == 'disconnect': disconnected = True
        if stop in {'cancel', 'disconnect'}:
            with pytest.raises(asyncio.CancelledError): await asyncio.wait_for(task, 1)
        else:
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as caught: await asyncio.wait_for(task, 1)
            assert caught.value.status_code == 504
        assert state.cancelled.is_set()
    asyncio.run(scenario())
    rows, audits = records()
    assert rows[0]['status'] == 'failed' and rows[0]['reserved_size_gb'] == 0
    assert audits[-1]['action'] == 'movie_request_submission_failed'


@pytest.mark.parametrize('duplicate', ['mediahub', 'available', 'queued'])
def test_duplicate_detection_remains_intact(setup, duplicate):
    state, _, _ = setup
    async def scenario():
        if duplicate == 'mediahub':
            assert (await download(await discover())).status_code == 200
            state.pushed = False
        else:
            state.mode = duplicate
        response = await download(await discover())
        assert response.status_code == 409
    asyncio.run(scenario())
    assert not state.pushed
    assert len(records()[0]) == (1 if duplicate == 'mediahub' else 0)


def test_radarr_source_keeps_fresh_search_and_guid_grab(setup):
    state, _, _ = setup
    state.mode = 'radarr'
    release = RadarrClient.normalise_release({**RAW, 'indexerId': 21, 'approved': True,
                                              'downloadAllowed': True, 'quality': {'quality': {'name': 'WEBDL-1080p'}}})
    token = main.cache_release(MOVIE['tmdb_id'], USER.user_id, release)
    response = asyncio.run(download(token))
    assert response.status_code == 200, response.text
    assert ('POST', '/api/v3/release', {'guid': RAW['guid'], 'indexerId': 21}) in state.calls
    assert not state.pushed


def test_storage_rejection_never_submits_release(setup, monkeypatch):
    state, _, _ = setup
    monkeypatch.setattr(main, 'storage_snapshot', lambda db, size: {'accepted': False, 'request_reservation_gb': 0})
    async def scenario():
        response = await download(await discover())
        assert response.status_code == 200 and response.json()['request']['status'] == 'rejected'
    asyncio.run(scenario())
    assert not state.pushed and records()[0][0]['reserved_size_gb'] == 0


def test_cancellation_during_storage_write_does_not_orphan_reservation(setup, monkeypatch):
    state, _, _ = setup
    original = main.storage_snapshot
    entered, finish = threading.Event(), threading.Event()
    def slow_storage(db, size):
        entered.set()
        assert finish.wait(1)
        return original(db, size)
    monkeypatch.setattr(main, 'storage_snapshot', slow_storage)
    async def scenario():
        token = await discover()
        request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
        task = asyncio.create_task(endpoint.request_movie(MOVIE['tmdb_id'], main.MovieRequestCreate(release_token=token), USER, request))
        async def wait_for_storage():
            while not entered.is_set(): await asyncio.sleep(.001)
        await asyncio.wait_for(wait_for_storage(), 1)
        task.cancel()
        finish.set()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(scenario())
    assert not state.pushed
    assert records()[0][0]['reserved_size_gb'] == 0 and records()[0][0]['status'] == 'failed'


@pytest.mark.parametrize('fallback_enabled', [True, False])
def test_current_recent_fallback_rules_are_revalidated(setup, monkeypatch, fallback_enabled):
    from datetime import date, timedelta
    state, presets, tmdb = setup
    today = date.today()
    movie = {**MOVIE, 'year': str(today.year), 'release_date': (today - timedelta(days=7)).isoformat()}
    raw = {**RAW, 'title': f"The Donut King {today.year} HDCAM x264"}
    tmdb.details.return_value = movie
    monkeypatch.setattr(runtime, '_prowlarr_search', AsyncMock(return_value=[raw]))
    async def scenario():
        _, releases, _ = await runtime.search_movie_releases(MOVIE['tmdb_id'], preset_main.movie_rules(), USER.user_id, movie=movie)
        assert releases[0]['eligible'] and releases[0]['recent_quality_fallback']
        presets['movies']['recent_release_fallback_enabled'] = fallback_enabled
        response = await download(releases[0]['release_token'])
        assert response.status_code == (200 if fallback_enabled else 422), response.text
    asyncio.run(scenario())
    assert state.pushed == fallback_enabled


def test_automatic_direct_fallback_uses_same_handoff(setup, monkeypatch):
    state, _, _ = setup
    async def fallback(*args, **kwargs):
        token = await discover()
        return {'id': 88}, [{'eligible': True, 'release_token': token}], False
    monkeypatch.setattr(enhanced_main, 'search_movie_releases', fallback)
    response = asyncio.run(download(None))
    assert response.status_code == 200 and response.json()['request']['status'] == 'queued'
    assert state.pushed
