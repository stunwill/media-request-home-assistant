"""Budgets and diagnostics shared by the effective Movie discovery pipeline."""
from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from time import monotonic

import httpx
from fastapi import HTTPException

SERVER_SECONDS = 18
PROVIDER_SECONDS = 6
MAPPING_SECONDS = 2
logger = logging.getLogger('mediahub.release_search')
metadata_cache: ContextVar[dict | None] = ContextVar('movie_search_metadata', default=None)
TIMEOUT_MESSAGE = 'Release search timed out. Prowlarr or an indexer is taking too long to respond. Check Setup and try again.'


async def stage(provider, tmdb_id, operation, seconds=None):
    started = monotonic()
    outcome = 'success'
    count = None
    try:
        async with asyncio.timeout(PROVIDER_SECONDS if seconds is None else seconds):
            result = await operation
        if isinstance(result, list):
            count = len(result)
        return result
    except (TimeoutError, asyncio.CancelledError) as error:
        outcome = 'cancelled' if isinstance(error, asyncio.CancelledError) else 'timeout'
        raise
    except Exception:
        outcome = 'error'
        raise
    finally:
        logger.info('release_search tmdb_id=%s provider=%s outcome=%s elapsed_ms=%s result_count=%s',
                    tmdb_id, provider, outcome, round((monotonic()-started)*1000), count)


async def movie_metadata(tmdb, tmdb_id):
    cache = metadata_cache.get()
    if cache is not None and tmdb_id in cache:
        return cache[tmdb_id]
    tmdb.timeout = httpx.Timeout(6, connect=3, pool=3)
    movie = await stage('tmdb', tmdb_id, tmdb.details(tmdb_id))
    if cache is not None:
        cache[tmdb_id] = movie
    return movie


def timeout_error():
    return HTTPException(status_code=504, detail=TIMEOUT_MESSAGE)
