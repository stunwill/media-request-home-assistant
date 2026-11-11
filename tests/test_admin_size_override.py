"""Exercise admin-only size approval through the deployed authenticated routes."""
import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from mediahub.app import watchlist_main, main, runtime, preset_main, release_identity_main, release_lifecycle, release_activity
from test_v01617_prowlarr_handoff import setup as setup, RAW, MOVIE, USER, records  # noqa: F401

LARGE = {**RAW, 'size': int(6.26 * 1024**3)}


@pytest.fixture(autouse=True)
def ample_test_disk(monkeypatch):
    monkeypatch.setattr(main.shutil, 'disk_usage', lambda _: SimpleNamespace(free=100 * 1024**3))


async def discover_large(monkeypatch, raw=None):
    monkeypatch.setattr(runtime, '_prowlarr_search', AsyncMock(return_value=[raw or LARGE]))
    _, releases, _ = await release_identity_main.search_movie_releases(
        MOVIE['tmdb_id'], preset_main.movie_rules(), USER.user_id, movie=MOVIE)
    return releases[0]


async def submit(item, **changes):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=watchlist_main.app), base_url='http://ingress.test') as client:
        return await client.post(f"/api/movies/{MOVIE['tmdb_id']}/request", json={
            'release_token': item.get('size_override_token'), 'allow_size_override': True,
            # Forged settings never override the server's household preset.
            'maximum_size_gb': 99, 'minimum_seeders': 0, **changes})


def test_explicit_approval_and_audit_outcome(setup, monkeypatch):
    state, presets, _ = setup
    before = copy.deepcopy(presets)
    async def scenario():
        item = await discover_large(monkeypatch)
        assert not item['eligible'] and item['size_override_available']
        assert not item.get('release_token') and item['maximum_size_gb'] == 3
        assert item['size_gb'] == pytest.approx(6.26, abs=.001)
        response = await submit(item)
        assert response.status_code == 200, response.text
        assert response.json()['request']['status'] == 'queued'
        assert (await submit(item)).status_code == 409
    asyncio.run(scenario())
    assert presets == before
    rows, audits = records()
    assert len(rows) == 1 and rows[0]['reserved_size_gb'] == round(6.26 * 1.5, 2)
    approval = json.loads(audits[0]['details_json'])['size_override']
    assert approval['approved'] is True and approval['configured_maximum_size_gb'] == 3
    assert approval['release_size_gb'] == pytest.approx(6.26, abs=.001)
    assert len(approval['release_id']) == 64
    assert audits[0]['actor_id'] == USER.user_id and audits[0]['occurred_at']
    assert json.loads(audits[-1]['details_json'])['size_override_approved'] is True
    assert 'private-test-secret' not in json.dumps(audits)
    assert len([x for x in state.calls if x[0] == 'POST' and x[1].endswith('/push')]) == 1


@pytest.mark.parametrize('role', ['requester', 'manager'])
def test_unauthorised_and_forged_role_rejected(setup, monkeypatch, role):
    state, _, tmdb = setup
    watchlist_main.app.dependency_overrides[main.current_user] = lambda: SimpleNamespace(
        user_id=USER.user_id, display_name=USER.display_name, role=role)
    async def scenario():
        item = await discover_large(monkeypatch)
        tmdb.details.reset_mock(); state.calls.clear()
        response = await submit(item, role='admin', user_id='admin')
        assert response.status_code == 403
        assert item['size_override_token'] in main.release_cache
    asyncio.run(scenario())
    assert not state.calls and not tmdb.details.await_count and records() == ([], [])


def test_explicit_flag_required_and_no_best_release_override(setup, monkeypatch):
    state, _, _ = setup
    async def scenario():
        item = await discover_large(monkeypatch)
        assert (await submit(item, allow_size_override=False)).status_code == 422
        assert (await submit({}, release_token=None)).status_code == 422
    asyncio.run(scenario())
    assert not state.pushed and records() == ([], [])


@pytest.mark.parametrize('change', ['seeders', 'resolution', 'conflicting_id', 'wrong_title', 'unknown_size', 'missing_link', 'mapping', 'preset'])
def test_other_restrictions_and_changed_preset_remain_enforced(setup, monkeypatch, change):
    state, presets, _ = setup
    async def scenario():
        item = await discover_large(monkeypatch)
        raw = main.release_cache[item['size_override_token']][3]
        if change == 'seeders': raw['seeders'] = 0
        if change == 'resolution': presets['movies']['allowed_resolutions'] = ['720p']
        if change == 'conflicting_id': raw['tmdb_id'] = 999999
        if change == 'wrong_title': raw['title'] = 'Other Movie 2020 1080p'
        if change == 'unknown_size': raw['size_gb'] = 0
        if change == 'missing_link': raw['download_url'] = ''
        if change == 'mapping': state.mapping = []
        if change == 'preset': presets['movies']['maximum_size_gb'] = 4
        response = await submit(item)
        assert response.status_code in {409, 422}, response.text
    asyncio.run(scenario())
    assert not state.pushed and records() == ([], [])


@pytest.mark.parametrize('changes', [{'seeders': 0}, {'title': RAW['title'].replace('1080p', '2160p')}, {'tmdbId': 999999}])
def test_discovery_offers_override_only_for_size_only_exclusions(setup, monkeypatch, changes):
    async def scenario():
        item = await discover_large(monkeypatch, {**LARGE, **changes})
        assert not item['eligible'] and not item.get('size_override_available')
        assert not item.get('release_token') and not item.get('size_override_token')
    asyncio.run(scenario())


@pytest.mark.parametrize('mode,expected', [('reject', 422), ('failure', 502), ('queued', 409), ('available', 409)])
def test_downstream_rejection_and_duplicates(setup, monkeypatch, mode, expected):
    state, _, _ = setup
    async def scenario():
        item = await discover_large(monkeypatch)
        state.mode = mode
        response = await submit(item)
        assert response.status_code == expected, response.text
        assert 'private-test-secret' not in response.text
    asyncio.run(scenario())
    rows, audits = records()
    if mode in {'reject', 'failure'}:
        assert rows[0]['status'] == 'failed' and rows[0]['reserved_size_gb'] == 0
        assert json.loads(audits[0]['details_json'])['size_override']['approved']
        assert audits[-1]['action'] == 'movie_request_submission_failed'
    else:
        assert rows == [] and not state.pushed


@pytest.mark.parametrize('role', ['admin', 'requester', 'manager'])
def test_public_response_permissions_and_diagnostic_counts(setup, monkeypatch, role):
    async def scenario():
        item = await discover_large(monkeypatch)
        monkeypatch.setattr(release_lifecycle, 'movie_details', AsyncMock(return_value={'lifecycle': {'state': 'released_unknown'}}))
        monkeypatch.setattr(release_activity, 'movie_releases', AsyncMock(return_value={'releases': [item]}))
        principal = SimpleNamespace(user_id=USER.user_id, display_name=USER.display_name, role=role)
        result = await release_lifecycle.release_search(MOVIE['tmdb_id'], preset_main.movie_rules(), principal, expanded=False)
        assert not result['releases'][0]['eligible']
        assert bool(result['releases'][0].get('size_override_token')) == (role == 'admin')
        if role == 'admin':
            assert result['discovery_diagnostics']['eligible_releases'] == 0
            assert result['discovery_diagnostics']['size_override_candidates'] == 1
            assert result['discovery_diagnostics']['final_unique_candidates'] == 1
    asyncio.run(scenario())


def test_selection_stays_bound_to_owner_movie_and_expiry(setup, monkeypatch):
    async def scenario():
        for invalid in ['owner', 'movie', 'expired', 'altered']:
            item = await discover_large(monkeypatch)
            token = item['size_override_token']; cached = main.release_cache[token]
            if invalid == 'owner': main.release_cache[token] = (cached[0], cached[1], 'another-user', cached[3])
            if invalid == 'movie': main.release_cache[token] = (cached[0], 9999, cached[2], cached[3])
            if invalid == 'expired': main.release_cache[token] = (0, *cached[1:])
            if invalid == 'altered': item['size_override_token'] = token + 'altered'
            assert (await submit(item)).status_code == 409
    asyncio.run(scenario())
    assert records() == ([], [])


def test_approval_does_not_carry_to_later_request(setup, monkeypatch):
    async def scenario():
        item = await discover_large(monkeypatch)
        assert (await submit(item)).status_code == 200
        with main.connect_db() as db:
            db.execute("UPDATE requests SET status='failed'"); db.commit()
        item = await discover_large(monkeypatch)
        assert (await submit(item, allow_size_override=False)).status_code == 422
    asyncio.run(scenario())


@pytest.mark.parametrize('change,expected', [('none', 200), ('size', 409), ('identity', 409), ('cutoff', 422)])
def test_radarr_selection_is_refreshed_and_revalidated(setup, monkeypatch, change, expected):
    from mediahub.app.media_services import RadarrClient
    state, _, _ = setup
    state.mode = 'radarr'
    monkeypatch.setitem(RAW, 'size', LARGE['size'])
    selected = RadarrClient.normalise_release({**RAW, 'indexerId': 21, 'approved': True,
        'downloadAllowed': True, 'quality': {'quality': {'name': 'WEBDL-1080p'}}})
    assert main.release_with_policy(selected, preset_main.movie_rules())['size_override_available']
    selected['_size_override_limit_gb'] = 3
    token = main.cache_release(MOVIE['tmdb_id'], USER.user_id, selected)
    if change == 'size': monkeypatch.setitem(RAW, 'size', LARGE['size'] + 1)
    if change == 'identity': monkeypatch.setitem(RAW, 'tmdbId', 999999)
    if change == 'cutoff': monkeypatch.setitem(RAW, 'rejections', ['Existing file meets cutoff'])
    response = asyncio.run(submit({'size_override_token': token}))
    assert response.status_code == expected, response.text
    posts = [entry for entry in state.calls if entry[0] == 'POST']
    assert len(posts) == (1 if expected == 200 else 0)


def test_size_override_keeps_storage_restrictions(setup, monkeypatch):
    monkeypatch.setattr(main.shutil, 'disk_usage', lambda _: SimpleNamespace(free=1024**3))
    async def scenario():
        response = await submit(await discover_large(monkeypatch))
        assert response.status_code == 200
        assert response.json()['request']['status'] == 'rejected'
        assert response.json()['request']['rejection_reason'] == 'insufficient_storage'
    asyncio.run(scenario())
    assert not setup[0].pushed


def test_reported_cmrg_movie_discovery(setup, monkeypatch):
    movie = {'tmdb_id': 653712, 'imdb_id': 'tt10702148', 'title': 'The Killing of Two Lovers',
             'original_title': 'The Killing of Two Lovers', 'year': '2021'}
    raw = {**LARGE, 'title': 'The Killing of Two Lovers 2020 1080p AMZN WEB-DL DDP5 1 H264-CMRG', 'seeders': 2}
    monkeypatch.setattr(runtime, '_prowlarr_search', AsyncMock(return_value=[raw]))
    async def scenario():
        _, releases, _ = await release_identity_main.search_movie_releases(
            movie['tmdb_id'], preset_main.movie_rules(), USER.user_id, movie=movie)
        assert releases[0]['identity_status'] == 'accepted'
        assert releases[0]['size_override_available'] and not releases[0]['eligible']
    asyncio.run(scenario())


def test_simultaneous_override_submissions_do_not_duplicate(setup, monkeypatch):
    async def scenario():
        first = await discover_large(monkeypatch)
        second = await discover_large(monkeypatch)
        responses = await asyncio.gather(submit(first), submit(second))
        assert sorted(response.status_code for response in responses) == [200, 409]
    asyncio.run(scenario())
    assert len(records()[0]) == 1
    assert len([entry for entry in setup[0].calls if entry[0] == 'POST']) == 1


def test_radarr_rejection_reason_is_shown_and_redacted(setup, monkeypatch):
    setup[0].mode = 'reject'
    _, radarr, _ = main.configured_clients({})
    original = radarr._request
    async def request(method, path, **kwargs):
        result = await original(method, path, **kwargs)
        if path.endswith('/release/push'):
            result[0]['rejections'] = ['Existing file meets cutoff', 'See https://private.test/?apikey=private-test-secret']
        return result
    monkeypatch.setattr(radarr, '_request', request)
    async def scenario():
        response = await submit(await discover_large(monkeypatch))
        assert response.status_code == 422
        assert 'Existing file meets cutoff' in response.text
        assert 'private-test-secret' not in response.text
    asyncio.run(scenario())
