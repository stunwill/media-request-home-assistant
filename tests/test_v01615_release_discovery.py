"""Behavioural tests use the deployed entrypoint, not a pre-patch helper."""
import asyncio
import re
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException

from mediahub.app import (
    main, enhanced_main, preset_main, movie_release_endpoint as endpoint, release_lifecycle, release_identity_main,
    release_search_control as control, runtime, watchlist_main,
)

MOVIE = {'tmdb_id': 653574, 'title': 'The Donut King', 'original_title': 'The Donut King',
         'year': '2020', 'release_date': '2020-10-30'}
RAW = {'guid': 'donut-guid', 'indexerId': 1, 'indexer': 'IPTorrents',
       'title': 'The Donut King 2020 1080p WEBRip x265', 'size': int(1.53*1024**3), 'seeders': 169}


def run(coro):
    return asyncio.run(coro)


def test_final_route_and_capture_graph():
    route = next(r for r in watchlist_main.app.routes if r.path == '/api/movies/{tmdb_id}/releases')
    assert watchlist_main.app.version == "0.16.16"
    assert route.endpoint is endpoint.movie_releases
    assert route.dependant.call is endpoint.movie_releases
    assert release_identity_main._original_search_movie_releases is runtime.search_movie_releases
    assert runtime._original_search_movie_releases.__module__.endswith('enhanced_main')


@pytest.mark.parametrize('hung', ['movie', 'broad', 'both', 'none', 'auth'])
def test_prowlarr_sibling_timeouts_preserve_results_and_cancel(hung):
    async def scenario():
        cancelled = []
        async def fake_get(self, path, params=None):
            kind = 'movie' if 'categories' in params else 'broad'
            if hung in {kind, 'both'}:
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.append(kind)
            code = 401 if hung == 'auth' and kind == 'movie' else 200
            return httpx.Response(code, json=[RAW], request=httpx.Request('GET', 'http://prowlarr.test/search'))
        with patch.object(main, 'load_options', return_value={'integrations': {
            'prowlarr_url': 'http://prowlarr.test', 'prowlarr_api_key': 'private-test-key'}}), \
             patch.object(httpx.AsyncClient, 'get', fake_get), patch.object(control, 'PROVIDER_SECONDS', .02):
            if hung in {'both', 'auth'}:
                with pytest.raises(HTTPException) as caught:
                    await runtime._prowlarr_search(MOVIE)
                assert caught.value.status_code == (504 if hung == 'both' else 503)
            else:
                results = await runtime._prowlarr_search(MOVIE)
                assert len(results) == 1
                assert results[0]['title'] == RAW['title']
        assert len(cancelled) == len(runtime._movie_search_terms(MOVIE)) * (2 if hung == 'both' else 1 if hung in {'movie', 'broad'} else 0)
    run(scenario())


@pytest.mark.parametrize('kind', ['radarr', 'fallback', 'mapping', 'radarr_hang', 'empty'])
def test_runtime_radarr_fallback_mapping_and_zero_results(kind):
    async def scenario():
        cancelled = []
        async def original(*args, **kwargs):
            if kind == 'radarr_hang':
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.append('radarr')
            return {'id': 88}, ([{'title': RAW['title'], 'eligible': True}] if kind == 'radarr' else []), False
        async def mapping(*args, **kwargs):
            if kind == 'mapping':
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.append('mapping')
            return [{'id': 21, 'name': 'IPTorrents'}]
        radarr = SimpleNamespace(ensure_movie=AsyncMock(return_value={'id': 88}), _request=mapping)
        with patch.object(runtime, '_original_search_movie_releases', original), \
             patch.object(runtime, '_prowlarr_search', AsyncMock(return_value=[] if kind == 'empty' else [RAW])), \
             patch.object(main, 'configured_clients', return_value=(None, radarr, None)), \
             patch.object(main, 'load_options', return_value={}), \
             patch.object(control, 'PROVIDER_SECONDS', .02), patch.object(control, 'MAPPING_SECONDS', .02):
            if kind == 'mapping':
                with pytest.raises(HTTPException) as caught:
                    await runtime.search_movie_releases(MOVIE['tmdb_id'], main.ReleaseRules(), 'test', movie=MOVIE)
                assert caught.value.status_code == 504
                assert cancelled == ['mapping']
            else:
                _, releases, _ = await runtime.search_movie_releases(MOVIE['tmdb_id'], main.ReleaseRules(), 'test', movie=MOVIE)
                assert len(releases) == (0 if kind == 'empty' else 1)
                if kind == 'radarr_hang':
                    assert cancelled == ['radarr']
                    assert releases[0]['eligible']
    run(scenario())


@pytest.mark.parametrize('stop', ['deadline', 'disconnect', 'caller'])
def test_final_endpoint_cancels_downstream_and_event_loop_remains_live(stop):
    async def scenario():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        ticks = 0
        async def pending(*args, **kwargs):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        async def ticker():
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(.001)
        request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
        with patch.object(release_lifecycle, 'release_search', pending), patch.object(control, 'SERVER_SECONDS', .04 if stop == 'deadline' else .4):
            heartbeat = asyncio.create_task(ticker())
            task = asyncio.create_task(endpoint.movie_releases(653574, main.ReleaseRules(), None, request, False, False))
            await entered.wait()
            if stop == 'disconnect':
                request.is_disconnected.return_value = True
            if stop == 'caller':
                await asyncio.sleep(.01)
                task.cancel()
            try:
                if stop == 'deadline':
                    with pytest.raises(HTTPException) as caught:
                        await task
                    assert caught.value.status_code == 504
                else:
                    with pytest.raises(asyncio.CancelledError):
                        await task
                assert cancelled.is_set()
                assert ticks >= 2
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
        assert control.metadata_cache.get() is None
    run(scenario())


def test_disconnect_cancels_actual_radarr_http_transport():
    async def scenario():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        async def transport(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        radarr = runtime.media_services.RadarrClient('http://radarr.test', 'secret', transport=httpx.MockTransport(transport))
        async def discover(*args, **kwargs):
            await radarr.ensure_movie(653574)
        request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
        with patch.object(release_lifecycle, 'release_search', discover):
            task = asyncio.create_task(endpoint.movie_releases(653574, main.ReleaseRules(), None, request, False, False))
            await entered.wait()
            request.is_disconnected.return_value = True
            with pytest.raises(asyncio.CancelledError):
                await task
            assert cancelled.is_set()
    run(scenario())


def test_settings_and_sqlite_do_not_block_search_event_loop():
    async def scenario():
        def slow_options():
            time.sleep(.04)
            return {}
        def slow_watch(*args):
            time.sleep(.04)
            return None
        tmdb = SimpleNamespace(details=AsyncMock(return_value=dict(MOVIE)))
        with patch.object(main, 'load_options', slow_options), \
             patch.object(main, 'configured_clients', return_value=(tmdb, None, None)), \
             patch.object(release_lifecycle, '_read_watch', slow_watch):
            work = asyncio.create_task(release_lifecycle.movie_details(653574, SimpleNamespace(user_id='test')))
            await asyncio.sleep(.01)
            assert not work.done()
            result = await work
            assert result['title'] == 'The Donut King'
    run(scenario())


def test_metadata_is_request_local_and_reused():
    async def scenario():
        tmdb = SimpleNamespace(details=AsyncMock(return_value=dict(MOVIE)))
        token = control.metadata_cache.set({})
        try:
            assert await control.movie_metadata(tmdb, 653574) is await control.movie_metadata(tmdb, 653574)
            assert tmdb.details.await_count == 1
        finally:
            control.metadata_cache.reset(token)
    run(scenario())


def test_structured_logging_has_no_credentials(caplog):
    async def scenario():
        with caplog.at_level('INFO', logger='mediahub.release_search'):
            await control.stage('radarr', 653574, AsyncMock(return_value=[])())
    run(scenario())
    assert 'tmdb_id=653574' in caplog.text
    assert 'provider=radarr' in caplog.text
    assert 'elapsed_ms=' in caplog.text
    assert 'result_count=0' in caplog.text
    assert 'private-test-key' not in caplog.text


def test_composed_javascript_behaviour(tmp_path):
    html = tmp_path/'deployed.html'
    html.write_text(main.INDEX_HTML)
    # Syntax-check every composed inline script, including extension overrides.
    for i, script in enumerate(re.findall(r'<script[^>]*>(.*?)</script>', main.INDEX_HTML, re.S)):
        source = tmp_path/f'script-{i}.js'
        source.write_text(script)
        subprocess.run(['node', '--check', str(source)], check=True, capture_output=True)
    result = subprocess.run(['node', 'tests/release_search_ui.cjs', str(html)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('hung', [False, True, 'all'])
def test_actual_asgi_endpoint_presets_identity_metadata_and_health(hung):
    async def scenario():
        principal = SimpleNamespace(user_id='test', display_name='Test', role='admin')
        tmdb = SimpleNamespace(details=AsyncMock(return_value=dict(MOVIE)))
        radarr = SimpleNamespace(
            ensure_movie=AsyncMock(return_value={'id': 88}), releases=AsyncMock(return_value=[]),
            _request=AsyncMock(return_value=[{'id': 21, 'name': 'IPTorrents'}]))
        cancelled = asyncio.Event()
        radarr_cancelled = asyncio.Event()
        async def hung_radarr(*args):
            try:
                await asyncio.Event().wait()
            finally:
                radarr_cancelled.set()
        if hung == 'all':
            radarr.releases = hung_radarr
        async def prowlarr(movie):
            if hung:
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return [RAW, {**RAW, 'guid': 'large', 'title': 'The Donut King 2020 1080p BluRay', 'size': 8*1024**3},
                    {**RAW, 'guid': 'tv', 'title': 'The Donut King S01E01 1080p WEB-DL'}]
        app = watchlist_main.app
        app.dependency_overrides[main.current_user] = lambda: principal
        try:
            with patch.object(main, 'configured_clients', return_value=(tmdb, radarr, None)), \
                 patch.object(main, 'load_options', return_value={}), \
                 patch.object(preset_main, 'load_presets', return_value=preset_main.DEFAULT_PRESETS), \
                 patch.object(release_lifecycle, '_read_watch', return_value=None), \
                 patch.object(enhanced_main, '_audit_release_search'), \
                 patch.object(runtime, '_prowlarr_search', prowlarr), \
                 patch.object(control, 'SERVER_SECONDS', .1 if hung else 1):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://ha.test') as client:
                    work = asyncio.create_task(client.post('/api/movies/653574/releases', json={
                        'maximum_size_gb': 100, 'minimum_seeders': 0}))
                    await asyncio.sleep(.02)
                    health = await client.get('/api/health')
                    assert health.status_code == 200
                    response = await asyncio.wait_for(work, timeout=2)
                if hung:
                    assert response.status_code == 504
                    assert cancelled.is_set()
                    if hung == 'all':
                        assert radarr_cancelled.is_set()
                    assert 'Release search timed out.' in response.json()['detail']
                else:
                    assert response.status_code == 200
                    result = response.json()
                    assert result['search_state'] == 'results'
                    assert len(result['releases']) == 3
                    eligible = [item for item in result['releases'] if item['eligible']]
                    assert len(eligible) == 1
                    assert eligible[0]['title'] == RAW['title']
                    assert not any(item['eligible'] for item in result['releases'] if 'S01E01' in item['title'])
                assert tmdb.details.await_count == 1
        finally:
            app.dependency_overrides.pop(main.current_user, None)
    run(scenario())
