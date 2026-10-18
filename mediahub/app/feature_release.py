"""v0.17 entry point extensions, installed after the existing effective routes."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from time import monotonic
from typing import Literal

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field

import httpx

from . import release_search_control, critic_ratings as ratings, download_history, enhanced_main, main, movie_release_endpoint, tv_main, tv_release_selection

app = main.app
app.version = '0.17.0'


def startup():
    download_history.initialise()
    ratings.initialise()


app.add_event_handler('startup', startup)
app.add_api_route('/api/download-history', download_history.history, methods=['GET'])


class RatingBatch(BaseModel):
    media_type: Literal['movie', 'tv']
    ids: list[int] = Field(max_length=20)


async def lookup_score(kind, tmdb_id):
    if tmdb_id <= 0 or not ratings.api_key():
        return None
    try:
        ratings.initialise()
        with main.connect_db() as db:
            identity = db.execute('SELECT * FROM critic_identity WHERE media_type=? AND tmdb_id=?', (kind,tmdb_id)).fetchone()
        if identity and identity['expires_at'] > time.time():
            score = await ratings.score_for(identity['imdb_id'], kind)
            await asyncio.to_thread(ratings.save_catalogue_score,kind,tmdb_id,score)
            return score
        if kind == 'tv':
            client, _ = tv_main.tv_clients()
            payload = await client._get(f'/tv/{tmdb_id}/external_ids')
        else:
            client, _, _ = main.configured_clients(main.load_options())
            payload = await client._get(f'/movie/{tmdb_id}/external_ids')
        with main.connect_db() as db:
            db.execute('INSERT OR REPLACE INTO critic_identity VALUES(?,?,?,?)', (kind,tmdb_id,payload.get('imdb_id'),time.time()+ratings.TTL))
        score = await ratings.score_for(payload.get('imdb_id'), kind)
        await asyncio.to_thread(ratings.save_catalogue_score, kind, tmdb_id, score)
        return score
    except (main.MediaServiceError, TimeoutError):
        return None


async def rating_batch(payload: RatingBatch, _: main.CurrentUser):
    scores = {}
    # Hard wall deadline and sequential bounded work, never background fan-out.
    try:
        async with asyncio.timeout(10):
            for tmdb_id in dict.fromkeys(payload.ids):
                scores[str(tmdb_id)] = await lookup_score(payload.media_type, tmdb_id)
    except TimeoutError:
        pass
    return {'scores': scores, 'configured': bool(ratings.api_key())}


app.add_api_route('/api/critic-ratings', rating_batch, methods=['POST'])


async def omdb_status(_: main.Administrator):
    return {'configured': bool(ratings.api_key()), 'provider': 'OMDb', 'daily_budget': ratings.DAILY_BUDGET}


async def omdb_test(_: main.Administrator):
    if not ratings.api_key():
        return {'status': 'not_configured', 'message': 'Save an OMDb API key first.'}
    if not ratings.reserve_request():
        return {'status':'warning', 'message':'Daily MediaHub metadata budget reached.'}
    try:
        payload = await ratings.fetch_omdb('tt0111161', ratings.api_key())
        connected = isinstance(payload, dict) and payload.get('Response') == 'True' and payload.get('imdbID') == 'tt0111161'
        return {'status': 'connected' if connected else 'error', 'message': 'OMDb connected.' if connected else 'OMDb rejected the request. Check your key or provider quota.'}
    except (httpx.HTTPError, ValueError, TimeoutError):
        return {'status': 'error', 'message':'OMDb unavailable. Check your key and try again.'}


app.add_api_route('/api/setup/omdb', omdb_status, methods=['GET'])
app.add_api_route('/api/setup/omdb/test', omdb_test, methods=['POST'])


async def catalogue(kind, principal, query, page, collection, genres, year_from, year_to, rating_from, rating_to, rt_min, rt_max):
    scope = ratings.scope_key(kind, query, collection)
    if rt_min is not None or rt_max is not None:
        return await asyncio.to_thread(ratings.filtered_catalogue, scope, kind, page, rt_min, rt_max, genres, year_from, year_to, rating_from, rating_to)
    if kind == 'tv':
        result = await tv_main.tv_catalogue(principal, query=query, page=page, collection=collection,
            genre_id=genres[0] if genres else None, year_from=year_from, year_to=year_to, rating_from=rating_from, rating_to=rating_to)
    else:
        result = await main.movie_catalogue(principal, query=query, page=page, collection=collection,
            genre_id=genres, year_from=year_from, year_to=year_to, rating_from=rating_from, rating_to=rating_to)
    await asyncio.to_thread(ratings.remember_catalogue, scope, kind, result.get('shows' if kind == 'tv' else 'movies') or [])
    return result


async def movie_catalogue(principal: main.CurrentUser, query: str = Query('', max_length=200), page: int = Query(1, ge=1, le=500),
    collection: Literal['popular','top_rated','now_playing','upcoming'] = 'popular', genre_id: list[int] | None = Query(None),
    year_from: int | None = Query(None, ge=1874, le=2100), year_to: int | None = Query(None, ge=1874, le=2100),
    rating_from: float | None = Query(None, ge=1, le=10), rating_to: float | None = Query(None, ge=1, le=10),
    rt_min: int | None = Query(None, ge=0, le=100), rt_max: int | None = Query(None, ge=0, le=100)):
    return await catalogue('movie',principal,query,page,collection,genre_id,year_from,year_to,rating_from,rating_to,rt_min,rt_max)


async def tv_catalogue(principal: main.CurrentUser, query: str = Query('', max_length=200), page: int = Query(1, ge=1, le=500),
    collection: Literal['popular','airing_today','on_the_air','top_rated'] = 'popular', genre_id: int | None = Query(None, ge=1),
    year_from: int | None = Query(None, ge=1874, le=2100), year_to: int | None = Query(None, ge=1874, le=2100),
    rating_from: float | None = Query(None, ge=1, le=10), rating_to: float | None = Query(None, ge=1, le=10),
    rt_min: int | None = Query(None, ge=0, le=100), rt_max: int | None = Query(None, ge=0, le=100)):
    return await catalogue('tv',principal,query,page,collection,[genre_id] if genre_id else [],year_from,year_to,rating_from,rating_to,rt_min,rt_max)


enhanced_main._replace_route('/api/catalog/movies', 'GET', movie_catalogue)
enhanced_main._replace_route('/api/catalog/tv', 'GET', tv_catalogue)

# Discovery caches are user and complete-settings scoped because release tokens
# are user-bound. Successful results only; forced refresh bypasses the cache.
_release_cache = {}
_release_locks = {}


async def cached_discovery(key, operation, force):
    now = monotonic()
    if len(_release_cache) > 256:
        _release_cache.clear()
    for old in list(_release_cache):
        if _release_cache[old][0] < now:
            _release_cache.pop(old, None)
    lock = _release_locks.setdefault(key, asyncio.Lock())
    try:
        async with lock:
            cached = _release_cache.get(key)
            if not force and cached and cached[0] > monotonic():
                return cached[1]
            discovery_token = release_search_control.discovery_only.set(True)
            try:
                async with asyncio.timeout(18):
                    result = await operation()
            except TimeoutError:
                raise HTTPException(504,'Release search timed out. Retry search.')
            finally:
                release_search_control.discovery_only.reset(discovery_token)
            if result.get('releases') and result.get('search_complete',True):
                _release_cache[key] = (monotonic()+120, result)
            return result
    finally:
        # Retain locks to avoid replacing one with queued waiters. Bound registry
        # using settings/owner key space in future if installations grow.
        if not lock.locked() and not getattr(lock, '_waiters', None):
            _release_locks.pop(key, None)


def discovery_key(kind, identifier, principal, flags):
    options = main.load_options()
    digest = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()
    return (kind, identifier, principal.user_id, principal.role, digest, flags)


async def movie_releases(tmdb_id: int, rules: main.ReleaseRules, principal: main.CurrentUser, request: Request,
    expanded: bool = False, manual_override: bool = False, refresh: bool = False):
    key = discovery_key('movie', tmdb_id, principal, (expanded,manual_override))
    return await movie_release_endpoint._until_disconnected(cached_discovery(key, lambda: movie_release_endpoint.movie_releases(tmdb_id,rules,principal,request,expanded,manual_override), refresh), request,tmdb_id,'cached_release_search')


async def season_releases(tmdb_id: int, season_number: int, principal: main.CurrentUser, request: Request, refresh: bool = False):
    async def operation():
        async with asyncio.timeout(18):
            return await tv_release_selection.season_releases(tmdb_id,season_number,principal)
    try:
        return await movie_release_endpoint._until_disconnected(
            cached_discovery(discovery_key('tv', (tmdb_id,season_number),principal,()),operation,refresh), request,tmdb_id,'tv_release_search')
    except TimeoutError:
        raise HTTPException(504,'TV release search timed out. Retry search.')


async def episode_releases(tmdb_id: int, season_number: int, episode_number: int, principal: main.CurrentUser, request: Request, refresh: bool = False):
    async def operation():
        async with asyncio.timeout(18):
            return await tv_release_selection.episode_releases(tmdb_id,season_number,episode_number,principal)
    try:
        return await movie_release_endpoint._until_disconnected(
            cached_discovery(discovery_key('tv', (tmdb_id,season_number,episode_number),principal,()),operation,refresh), request,tmdb_id,'tv_release_search')
    except TimeoutError:
        raise HTTPException(504,'TV release search timed out. Retry search.')


enhanced_main._replace_route('/api/movies/{tmdb_id}/releases','POST',movie_releases)
enhanced_main._replace_route('/api/catalog/tv/{tmdb_id}/seasons/{season_number}/releases','GET',season_releases)
enhanced_main._replace_route('/api/catalog/tv/{tmdb_id}/seasons/{season_number}/episodes/{episode_number}/releases','GET',episode_releases)

def invalidate_user_releases(user_id):
    for key in list(_release_cache):
        if key[2] == user_id:
            _release_cache.pop(key, None)


async def request_movie(tmdb_id: int, payload: main.MovieRequestCreate, principal: main.CurrentUser, request: Request):
    try:
        return await movie_release_endpoint.request_movie(tmdb_id,payload,principal,request)
    finally:
        invalidate_user_releases(principal.user_id)


async def grab_tv_release(payload: tv_release_selection.TvGrabRequest, principal: main.CurrentUser, request: Request):
    async def operation():
        try:
            async with asyncio.timeout(18):
                return await tv_release_selection.grab_tv_release(payload,principal)
        except TimeoutError:
            raise HTTPException(504,'Sonarr submission timed out. Check Downloads before trying again.')
        finally:
            invalidate_user_releases(principal.user_id)
    return await movie_release_endpoint._until_disconnected(operation(),request,0,'tv_handoff')


async def request_tv(tmdb_id: int, payload: tv_main.TvRequestCreate, principal: main.CurrentUser, request: Request):
    async def operation():
        try:
            async with asyncio.timeout(18):
                return await tv_main.request_tv(tmdb_id,payload,principal)
        except TimeoutError:
            raise HTTPException(504,'Sonarr submission timed out. Check Downloads before trying again.')
        finally:
            invalidate_user_releases(principal.user_id)
    return await movie_release_endpoint._until_disconnected(operation(),request,tmdb_id,'tv_request')


enhanced_main._replace_route('/api/movies/{tmdb_id}/request','POST',request_movie)
enhanced_main._replace_route('/api/tv/releases/grab','POST',grab_tv_release)
enhanced_main._replace_route('/api/tv/{tmdb_id}/request','POST',request_tv)

from .feature_ui import FEATURE_UI  # noqa: E402
main.INDEX_HTML = main.INDEX_HTML.replace('</body>', FEATURE_UI + '\n</body>')
