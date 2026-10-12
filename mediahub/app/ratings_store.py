"""Persistent per-source states and finite, lease-based background enrichment."""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from datetime import UTC, datetime

from . import main, ratings_providers as providers, tv_main
from .schema_migrations import serialised

EXTERNAL = {'mdblist':('imdb','rt_critic','rt_audience','metacritic','letterboxd','trakt'),
            'omdb':('imdb','rt_critic','metacritic')}
_tasks = set()


def configuration():
    raw = main.load_options().get('ratings', {})
    return {'cache_days':max(1,min(30,int(raw.get('cache_days',7)))),
            'daily_budget':max(0,min(900,int(raw.get('daily_budget',400)))),
            'background_enabled':bool(raw.get('background_enabled',True))}


def key(provider):
    return str(main.load_options().get('integrations',{}).get(provider+'_api_key') or '').strip()


@serialised
def initialise():
    with main.connect_db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS rating_titles (
          kind TEXT NOT NULL, tmdb_id INTEGER NOT NULL, imdb_id TEXT, payload TEXT NOT NULL,
          first_seen REAL NOT NULL, PRIMARY KEY(kind,tmdb_id));
        CREATE TABLE IF NOT EXISTS rating_values (
          kind TEXT NOT NULL, tmdb_id INTEGER NOT NULL, provider TEXT NOT NULL,
          source TEXT NOT NULL, value REAL, votes INTEGER, status TEXT NOT NULL,
          retrieved REAL NOT NULL, expires REAL NOT NULL, error TEXT,
          PRIMARY KEY(kind,tmdb_id,provider,source));
        CREATE INDEX IF NOT EXISTS idx_rating_filter ON rating_values(source,status,value,votes);
        CREATE TABLE IF NOT EXISTS rating_jobs (
          kind TEXT NOT NULL, tmdb_id INTEGER NOT NULL, provider TEXT NOT NULL,
          state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
          next_run REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0,
          PRIMARY KEY(kind,tmdb_id,provider));
        CREATE TABLE IF NOT EXISTS rating_health (
          provider TEXT PRIMARY KEY, status TEXT NOT NULL, last_success REAL,
          last_error TEXT, blocked_until REAL NOT NULL DEFAULT 0, metadata TEXT);
        CREATE TABLE IF NOT EXISTS rating_budget (
          provider TEXT NOT NULL, day TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(provider,day));
        ''')
        tables={row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if {'critic_cache','critic_identity','critic_catalogue'} <= tables:
            db.execute('''INSERT OR IGNORE INTO rating_titles SELECT media_type,tmdb_id,NULL,payload,seen_at
                FROM critic_catalogue ORDER BY seen_at DESC''')
            db.execute('''INSERT OR IGNORE INTO rating_values
              SELECT i.media_type,i.tmdb_id,'omdb','rt_critic',c.score,NULL,'verified',c.checked_at,c.expires_at,NULL
              FROM critic_identity i JOIN critic_cache c ON c.imdb_id=i.imdb_id AND c.media_type=i.media_type
              WHERE c.score IS NOT NULL''')


def ingest(kind, items):
    now = time.time()
    with main.connect_db() as db:
        for item in items:
            if not item.get('tmdb_id'):
                continue
            imdb = item.get('imdb_id') or (item.get('external_ids') or {}).get('imdb_id')
            previous = db.execute('SELECT payload FROM rating_titles WHERE kind=? AND tmdb_id=?',(kind,item['tmdb_id'])).fetchone()
            merged = {**(json.loads(previous['payload']) if previous else {}),**item}
            db.execute('''INSERT INTO rating_titles VALUES(?,?,?,?,?) ON CONFLICT(kind,tmdb_id)
              DO UPDATE SET payload=excluded.payload,imdb_id=COALESCE(excluded.imdb_id,rating_titles.imdb_id)''',
              (kind,item['tmdb_id'],imdb,json.dumps(merged),now))
            value = providers.number(item.get('rating_raw',item.get('rating')),10)
            db.execute('INSERT OR REPLACE INTO rating_values VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (kind,item['tmdb_id'],'tmdb','tmdb',value,providers.votes(item.get('vote_count')),
                        'verified' if value is not None else 'unavailable',now,now+configuration()['cache_days']*86400,None))
    enqueue(kind,[item['tmdb_id'] for item in items if item.get('tmdb_id')])


def enqueue(kind, ids, force=False):
    accepted = 0
    now = time.time()
    with main.connect_db() as db:
        db.execute('BEGIN IMMEDIATE')
        outstanding = db.execute("SELECT COUNT(*) n FROM rating_jobs WHERE state IN ('pending','running')").fetchone()['n']
        for tmdb_id in dict.fromkeys(ids[:100]):
            for provider in EXTERNAL:
                if not key(provider) or outstanding >= 400:
                    continue
                latest = db.execute('SELECT MIN(expires) expires FROM rating_values WHERE kind=? AND tmdb_id=? AND provider=?',(kind,tmdb_id,provider)).fetchone()['expires']
                if not force and latest and latest > now:
                    continue
                job = db.execute('SELECT * FROM rating_jobs WHERE kind=? AND tmdb_id=? AND provider=?',(kind,tmdb_id,provider)).fetchone()
                if job and (job['state'] in {'pending','running'} or not force and job['next_run'] > now):
                    continue
                db.execute("INSERT OR REPLACE INTO rating_jobs VALUES(?,?,?,'pending',0,?,0)",(kind,tmdb_id,provider,now))
                accepted += 1
                outstanding += 1
    return accepted


def snapshot(kind, ids):
    result = {str(tmdb_id):{} for tmdb_id in ids}
    now = time.time()
    preference = {'tmdb':0,'mdblist':1,'omdb':2}
    with main.connect_db() as db:
        for tmdb_id in ids:
            rows = db.execute('SELECT * FROM rating_values WHERE kind=? AND tmdb_id=?',(kind,tmdb_id)).fetchall()
            for row in sorted(rows,key=lambda r:preference.get(r['provider'],3)):
                entry = dict(row)
                entry['status'] = 'expired' if entry['expires'] <= now else entry['status']
                current = result[str(tmdb_id)].get(entry['source'])
                if current and current['status'] == 'verified':
                    continue
                result[str(tmdb_id)][entry['source']] = entry
            for source in providers.SOURCES:
                result[str(tmdb_id)].setdefault(source,{'source':source,'status':'not_retrieved','value':None,'votes':None})
    return result


def claim():
    now = time.time()
    with main.connect_db() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("UPDATE rating_jobs SET state='pending' WHERE state='running' AND lease_until<?",(now,))
        job = db.execute("SELECT * FROM rating_jobs WHERE state='pending' AND next_run<=? ORDER BY next_run,tmdb_id LIMIT 1",(now,)).fetchone()
        if job:
            db.execute("UPDATE rating_jobs SET state='running',lease_until=?,attempts=attempts+1 WHERE kind=? AND tmdb_id=? AND provider=?",(now+90,job['kind'],job['tmdb_id'],job['provider']))
    return dict(job) if job else None


def reserve(provider):
    day = datetime.now(UTC).date().isoformat()
    now = time.time()
    with main.connect_db() as db:
        db.execute('BEGIN IMMEDIATE')
        health = db.execute('SELECT * FROM rating_health WHERE provider=?',(provider,)).fetchone()
        if health and health['blocked_until'] > now:
            raise providers.ProviderFailure(health['status'],health['blocked_until']-now)
        db.execute('INSERT OR IGNORE INTO rating_budget VALUES(?,?,0)',(provider,day))
        used = db.execute('SELECT used FROM rating_budget WHERE provider=? AND day=?',(provider,day)).fetchone()['used']
        if used >= configuration()['daily_budget']:
            raise providers.ProviderFailure('rate_limited',86400-(now%86400))
        db.execute('UPDATE rating_budget SET used=used+1 WHERE provider=? AND day=?',(provider,day))


async def identity(kind, tmdb_id):
    with main.connect_db() as db:
        row = db.execute('SELECT imdb_id FROM rating_titles WHERE kind=? AND tmdb_id=?',(kind,tmdb_id)).fetchone()
    if row and row['imdb_id']:
        return row['imdb_id']
    if kind == 'tv':
        client,_ = tv_main.tv_clients()
    else:
        client,_,_ = main.configured_clients(main.load_options())
    payload = await client._get(f'/{"tv" if kind == "tv" else "movie"}/{tmdb_id}/external_ids')
    imdb = payload.get('imdb_id')
    with main.connect_db() as db:
        db.execute('UPDATE rating_titles SET imdb_id=? WHERE kind=? AND tmdb_id=?',(imdb,kind,tmdb_id))
    return imdb


async def process(job):
    kind,tmdb_id,provider = job['kind'],job['tmdb_id'],job['provider']
    now = time.time()
    metadata = {}
    status,error,values,delay = 'verified',None,{},configuration()['cache_days']*86400
    try:
        if not key(provider):
            raise providers.ProviderFailure('not_configured',3600)
        await asyncio.to_thread(reserve,provider)
        async with asyncio.timeout(12):
            imdb = await identity(kind,tmdb_id)
            payload,metadata = await providers.fetch(provider,key(provider),kind,tmdb_id,imdb)
            values = providers.normalise_omdb(payload,kind,imdb) if provider == 'omdb' else providers.normalise_mdblist(payload,kind,tmdb_id,imdb)
    except providers.ProviderFailure as failure:
        status = failure.status
        error = status  # Never persist provider text, URLs, headers or credentials.
        delay = failure.retry_after
    except (TimeoutError, main.MediaServiceError):
        status,error,delay = 'lookup_failed','metadata_unavailable',60
    with main.connect_db() as db:
        for source in EXTERNAL[provider]:
            value,vote_count = values.get(source,(None,None))
            state = 'verified' if value is not None else 'unavailable' if status == 'verified' else status
            old = db.execute('SELECT * FROM rating_values WHERE kind=? AND tmdb_id=? AND provider=? AND source=?',(kind,tmdb_id,provider,source)).fetchone()
            if old and old['value'] is not None and status != 'verified':
                # Preserve last known data and original retrieval/expiry on failure.
                db.execute('UPDATE rating_values SET error=? WHERE kind=? AND tmdb_id=? AND provider=? AND source=?',(error,kind,tmdb_id,provider,source))
            else:
                db.execute('INSERT OR REPLACE INTO rating_values VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (kind,tmdb_id,provider,source,value,vote_count,state,now,now+(86400 if state == 'unavailable' else delay),error))
        success = now if status == 'verified' else None
        block = now+delay if status in {'authentication_failed','rate_limited','temporarily_unavailable'} else 0
        db.execute('''INSERT INTO rating_health VALUES(?,?,?,?,?,?) ON CONFLICT(provider)
          DO UPDATE SET status=excluded.status,last_success=COALESCE(excluded.last_success,rating_health.last_success),
          last_error=excluded.last_error,blocked_until=excluded.blocked_until,metadata=excluded.metadata''',
          (provider,status,success,error,block,json.dumps(metadata)))
        transient = status in {'lookup_failed','temporarily_unavailable'} and job['attempts'] < 2
        db.execute('UPDATE rating_jobs SET state=?,next_run=?,lease_until=0 WHERE kind=? AND tmdb_id=? AND provider=?',
                   ('pending' if transient else 'done',now+delay*2**job['attempts'],kind,tmdb_id,provider))


async def worker():
    while True:
        if configuration()['background_enabled']:
            job = await asyncio.to_thread(claim)
            if job:
                try:
                    await process(job)
                except asyncio.CancelledError:
                    with main.connect_db() as db:
                        db.execute("UPDATE rating_jobs SET state='pending',lease_until=0 WHERE kind=? AND tmdb_id=? AND provider=?",(job['kind'],job['tmdb_id'],job['provider']))
                    raise
                except sqlite3.Error:
                    # Database failures are not provider failures. Keep the
                    # actual error visible rather than masking a migration bug.
                    logging.getLogger('mediahub.ratings').exception('Ratings database operation failed')
                    raise
                except Exception:
                    # Unexpected errors remain explicit, bounded and credential-safe.
                    with main.connect_db() as db:
                        db.execute("UPDATE rating_jobs SET state='failed',next_run=?,lease_until=0 WHERE kind=? AND tmdb_id=? AND provider=?",(time.time()+300,job['kind'],job['tmdb_id'],job['provider']))
                        db.execute('''INSERT INTO rating_health(provider,status,last_error,blocked_until)
                          VALUES(?,'lookup_failed','worker_error',?) ON CONFLICT(provider)
                          DO UPDATE SET status='lookup_failed',last_error='worker_error',blocked_until=excluded.blocked_until''',
                          (job['provider'],time.time()+300))
                await asyncio.sleep(0.5)  # At most two requests/sec per worker.
                continue
        await asyncio.sleep(1)


async def start():
    initialise()
    if not _tasks:
        task = asyncio.create_task(worker(),name='ratings-enrichment')
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


async def stop():
    for task in list(_tasks):
        task.cancel()
    await asyncio.gather(*list(_tasks),return_exceptions=True)
    _tasks.clear()


def health():
    with main.connect_db() as db:
        records = {row['provider']:dict(row) for row in db.execute('SELECT * FROM rating_health')}
        jobs = db.execute("SELECT state,COUNT(*) count FROM rating_jobs GROUP BY state").fetchall()
        total=db.execute('SELECT COUNT(*) n FROM rating_titles').fetchone()['n']
        coverage={row['status']:row['n'] for row in db.execute('SELECT status,COUNT(*) n FROM rating_values GROUP BY status')}
        expired=db.execute('SELECT COUNT(*) n FROM rating_values WHERE expires<=?',(time.time(),)).fetchone()['n']
    return {'providers':{provider:{**records.get(provider,{}),'configured':bool(key(provider)),
             'status':records.get(provider,{}).get('status','not_retrieved') if key(provider) else 'not_configured'} for provider in EXTERNAL},
            'jobs':{row['state']:row['count'] for row in jobs},'configuration':configuration(),
            'coverage':{'titles_inspected':total,'rating_records_by_status':coverage,'expired_rating_records':expired}}


def credentials_changed(provider):
    """A repaired key must not remain blocked by the previous key's failures."""
    with main.connect_db() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rating_health'").fetchone():
            return
        db.execute("UPDATE rating_health SET status='not_retrieved',last_error=NULL,blocked_until=0 WHERE provider=?",(provider,))
        db.execute("UPDATE rating_values SET expires=0 WHERE provider=? AND status NOT IN ('verified','unavailable')",(provider,))
        db.execute("UPDATE rating_jobs SET next_run=0 WHERE provider=? AND state NOT IN ('running','pending')",(provider,))
