"""Permitted API adapters, native rating scales and credential-safe errors."""
from __future__ import annotations

import logging
import math
import re

import httpx

SOURCES = {'tmdb':10, 'imdb':10, 'rt_critic':100, 'rt_audience':100,
           'metacritic':100, 'letterboxd':5, 'trakt':10}
LABELS = {'tmdb':'TMDb', 'imdb':'IMDb', 'rt_critic':'RT critics',
          'rt_audience':'RT audience', 'metacritic':'Metacritic',
          'letterboxd':'Letterboxd', 'trakt':'Trakt'}


class ProviderFailure(Exception):
    def __init__(self, status, retry_after=60):
        self.status = status
        self.retry_after = max(30, min(float(retry_after), 86400))
        super().__init__(status)


class RedactRatingRequests(logging.Filter):
    def filter(self, record):
        if any(host in record.getMessage() for host in ('omdbapi.com', 'api.mdblist.com')):
            record.msg, record.args = 'Ratings API request (credentials redacted)', ()
        return True


logging.getLogger('httpx').addFilter(RedactRatingRequests())


def number(value, maximum):
    try:
        result = float(str(value).removesuffix('%'))
        return result if math.isfinite(result) and 0 <= result <= maximum else None
    except (ValueError, TypeError):
        return None


def votes(value):
    try:
        result = int(str(value).replace(',', ''))
        return result if result >= 0 else None
    except (ValueError, TypeError):
        return None


def normalise_omdb(payload, kind, imdb_id):
    if payload.get('imdbID') != imdb_id or payload.get('Type') != ('series' if kind == 'tv' else 'movie'):
        raise ProviderFailure('identity_mismatch', 86400)
    values = {'imdb':(number(payload.get('imdbRating'),10),votes(payload.get('imdbVotes'))),
              'metacritic':(number(payload.get('Metascore'),100),None)}
    for rating in payload.get('Ratings') or []:
        if rating.get('Source') == 'Rotten Tomatoes':
            raw = str(rating.get('Value') or '')
            values['rt_critic'] = (number(raw,100) if re.fullmatch(r'\d{1,3}%',raw) else None,None)
    return values


def normalise_mdblist(payload, kind, tmdb_id, imdb_id=None):
    ids = payload.get('ids') or {}
    returned_tmdb = payload.get('tmdb_id') or payload.get('tmdbid') or ids.get('tmdb')
    returned_imdb = payload.get('imdb_id') or payload.get('imdbid') or ids.get('imdb')
    if returned_tmdb is not None and str(returned_tmdb) != str(tmdb_id):
        raise ProviderFailure('identity_mismatch',86400)
    if returned_imdb and imdb_id and returned_imdb != imdb_id:
        raise ProviderFailure('identity_mismatch',86400)
    if returned_tmdb is None and not (imdb_id and returned_imdb == imdb_id):
        raise ProviderFailure('identity_unverified',86400)
    if payload.get('type') not in (('show','series','tv') if kind == 'tv' else ('movie',)):
        raise ProviderFailure('identity_mismatch',86400)
    aliases = {'imdb':'imdb', 'tomatoes':'rt_critic', 'rottentomatoes':'rt_critic',
               'popcorn':'rt_audience', 'audience':'rt_audience', 'tomatoesaudience':'rt_audience',
               'metacritic':'metacritic', 'letterboxd':'letterboxd', 'trakt':'trakt'}
    result = {}
    for rating in payload.get('ratings') or []:
        source = aliases.get(str(rating.get('source') or '').lower())
        if source:
            result[source] = (number(rating.get('value'), SOURCES[source]), votes(rating.get('votes')))
    return result


async def fetch(provider, key, kind, tmdb_id, imdb_id):
    url = 'https://www.omdbapi.com/' if provider == 'omdb' else f'https://api.mdblist.com/tmdb/{"show" if kind == "tv" else "movie"}/{tmdb_id}/'
    params = {'apikey':key}
    if provider == 'omdb':
        if not imdb_id:
            raise ProviderFailure('identity_unavailable',86400)
        params['i'] = imdb_id
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5,connect=2)) as client:
            response = await client.get(url, params=params)
        if response.status_code == 429:
            try:
                delay = float(response.headers.get('Retry-After','300'))
            except ValueError:
                delay = 300
            raise ProviderFailure('rate_limited', delay)
        if response.status_code in {401,403}:
            raise ProviderFailure('authentication_failed',3600)
        if response.status_code == 404:
            raise ProviderFailure('unavailable',86400)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload,dict):
            raise ProviderFailure('invalid_response')
        if provider == 'omdb' and payload.get('Response') == 'False':
            error = str(payload.get('Error') or '').lower()
            status = 'authentication_failed' if 'key' in error else 'rate_limited' if 'limit' in error else 'unavailable'
            raise ProviderFailure(status,3600 if status != 'unavailable' else 86400)
        return payload, {k:response.headers[k] for k in ('X-RateLimit-Remaining','X-RateLimit-Reset') if k in response.headers}
    except (httpx.HTTPError, ValueError) as error:
        raise ProviderFailure('temporarily_unavailable') from error
