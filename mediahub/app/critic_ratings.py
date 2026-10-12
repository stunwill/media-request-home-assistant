"""Optional OMDb critic metadata. No scraping, title guessing or client secrets."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException

from . import main

DAILY_BUDGET = 400  # Shared by both HA workers, leaves room for other OMDb users.
TTL = 7 * 86400
NEGATIVE_TTL = 86400
_lock = asyncio.Lock()


class _HideOmdbRequest(logging.Filter):
    def filter(self, record):
        if 'omdbapi.com' in record.getMessage():
            record.msg = 'OMDb metadata request (credentials redacted)'
            record.args = ()
        return True


logging.getLogger('httpx').addFilter(_HideOmdbRequest())


from .schema_migrations import serialised  # noqa: E402


@serialised
def initialise():
    with main.connect_db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS critic_cache (
          imdb_id TEXT PRIMARY KEY, media_type TEXT NOT NULL, score INTEGER,
          checked_at REAL NOT NULL, expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS critic_identity (
          media_type TEXT NOT NULL, tmdb_id INTEGER NOT NULL, imdb_id TEXT,
          expires_at REAL NOT NULL, PRIMARY KEY(media_type,tmdb_id));
        CREATE TABLE IF NOT EXISTS critic_budget (
          day TEXT PRIMARY KEY, used INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS critic_catalogue (
          scope TEXT NOT NULL, media_type TEXT NOT NULL, tmdb_id INTEGER NOT NULL,
          payload TEXT NOT NULL, seen_at REAL NOT NULL,
          PRIMARY KEY(scope,media_type,tmdb_id));
        ''')


def extract_score(payload, imdb_id, kind):
    if payload.get('imdbID') != imdb_id or payload.get('Type') != ('series' if kind == 'tv' else 'movie'):
        return None
    for rating in payload.get('Ratings') or []:
        if rating.get('Source') == 'Rotten Tomatoes':
            match = re.fullmatch(r'(\d{1,3})%', str(rating.get('Value') or ''))
            if match and 0 <= int(match[1]) <= 100:
                return int(match[1])
    return None


def api_key():
    return str(main.load_options().get('integrations', {}).get('omdb_api_key') or '').strip()


def reserve_request():
    initialise()
    day = datetime.now(UTC).date().isoformat()
    with main.connect_db() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO critic_budget(day,used) VALUES(?,0)', (day,))
        used = db.execute('SELECT used FROM critic_budget WHERE day=?', (day,)).fetchone()['used']
        if used >= DAILY_BUDGET:
            return False
        db.execute('UPDATE critic_budget SET used=used+1 WHERE day=?', (day,))
    return True


async def fetch_omdb(imdb_id, key):
    # Never include provider errors or request URLs in responses or application logs.
    async with httpx.AsyncClient(timeout=httpx.Timeout(4, connect=2)) as client:
        response = await client.get('https://www.omdbapi.com/', params={'i': imdb_id, 'apikey': key})
        response.raise_for_status()
        return response.json()


async def score_for(imdb_id, kind):
    if not re.fullmatch(r'tt\d+', str(imdb_id or '')) or not api_key():
        return None
    # Serialise misses, recheck cache after acquiring, shared DB enforces daily cap.
    async with _lock:
        initialise()
        now = time.time()
        with main.connect_db() as db:
            row = db.execute('SELECT * FROM critic_cache WHERE imdb_id=? AND media_type=?', (imdb_id, kind)).fetchone()
        if row and row['expires_at'] > now:
            return row['score']
        if not reserve_request():
            return None
        try:
            payload = await fetch_omdb(imdb_id, api_key())
            if not isinstance(payload, dict):
                return None
            if payload.get('Response') == 'False':
                with main.connect_db() as db:
                    db.execute('INSERT OR REPLACE INTO critic_cache VALUES(?,?,?,?,?)', (imdb_id,kind,None,now,now+60))
                return None
            score = extract_score(payload, imdb_id, kind)
        except (httpx.HTTPError, ValueError, TimeoutError):
            with main.connect_db() as db:
                db.execute('INSERT OR REPLACE INTO critic_cache VALUES(?,?,?,?,?)', (imdb_id,kind,None,now,now+60))
            return None
        with main.connect_db() as db:
            db.execute('INSERT OR REPLACE INTO critic_cache VALUES(?,?,?,?,?)',
                       (imdb_id, kind, score, now, now + (TTL if score is not None else NEGATIVE_TTL)))
        return score


def scope_key(kind, query, collection):
    options = main.load_options()
    language = options.get('presets', {}).get('discovery', {}).get('original_language', 'en')
    return hashlib.sha256(json.dumps([kind, query.strip().casefold(), collection, language]).encode()).hexdigest()


def remember_catalogue(scope, kind, items):
    initialise()
    with main.connect_db() as db:
        for item in items:
            old = db.execute('SELECT payload FROM critic_catalogue WHERE scope=? AND media_type=? AND tmdb_id=?',
                             (scope, kind, item['tmdb_id'])).fetchone()
            payload = {**(json.loads(old['payload']) if old else {}), **item}
            db.execute('INSERT OR REPLACE INTO critic_catalogue VALUES(?,?,?,?,?)',
                       (scope, kind, item['tmdb_id'], json.dumps(payload), time.time()))
        db.execute('DELETE FROM critic_catalogue WHERE seen_at<?', (time.time()-30*86400,))


def save_catalogue_score(kind, tmdb_id, score):
    initialise()
    with main.connect_db() as db:
        rows = db.execute('SELECT scope,payload FROM critic_catalogue WHERE media_type=? AND tmdb_id=?', (kind, tmdb_id)).fetchall()
        for row in rows:
            item = json.loads(row['payload'])
            item['rt_score'] = score
            item['rt_checked_at'] = time.time()
            db.execute('UPDATE critic_catalogue SET payload=? WHERE scope=? AND media_type=? AND tmdb_id=?',
                       (json.dumps(item), row['scope'], kind, tmdb_id))


def filtered_catalogue(scope, kind, page, minimum, maximum, genres, year_from, year_to, rating_from, rating_to):
    if minimum is not None and maximum is not None and minimum > maximum:
        raise HTTPException(422, 'Rotten Tomatoes minimum must not exceed maximum.')
    initialise()
    with main.connect_db() as db:
        rows = db.execute('SELECT payload FROM critic_catalogue WHERE scope=? AND media_type=? ORDER BY seen_at DESC,tmdb_id', (scope, kind)).fetchall()
    items = []
    for row in rows:
        item = json.loads(row['payload'])
        score = item.get('rt_score')
        if score is None or item.get('rt_checked_at', 0) < time.time()-TTL:
            continue
        if minimum is not None and score < minimum or maximum is not None and score > maximum:
            continue
        year = int(item.get('year') or 0)
        rating = float(item.get('rating') or 0)
        if year_from and year < year_from or year_to and year > year_to:
            continue
        if rating_from and rating < rating_from or rating_to and rating > rating_to:
            continue
        if genres and not set(genres).issubset(set(item.get('genre_ids') or [])):
            continue
        items.append(item)
    return {'page': page, 'total_pages': max(1, (len(items)+19)//20), 'total_results': len(items),
            'shows' if kind == 'tv' else 'movies': items[(page-1)*20:page*20],
            'rt_scope': 'cached_verified', 'catalogue_notice': 'Rotten Tomatoes: verified cached titles for this catalogue/search only. Browse without score filters to extend coverage. Missing or expired scores are excluded; this is not the complete TMDB catalogue.'}
