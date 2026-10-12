"""Persistent, additive lifecycle evidence and bounded request-history paging."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from time import monotonic

from fastapi import Query

from . import main, tv_release_selection

_refresh_lock = asyncio.Lock()
_last_refresh = 0.0
_refresh_warning = None
FIELDS = {
    'download_started_at': 'TEXT', 'download_completed_at': 'TEXT', 'imported_at': 'TEXT',
    'actual_size_bytes': 'INTEGER', 'progress_known': 'INTEGER NOT NULL DEFAULT 0',
    'series_title': 'TEXT', 'available_observed_at': 'TEXT',
}


from .schema_migrations import serialised  # noqa: E402


@serialised
def initialise():
    with main.connect_db() as db:
        columns = {row['name'] for row in db.execute('PRAGMA table_info(requests)')}
        for name, definition in FIELDS.items():
            if name not in columns:
                db.execute(f'ALTER TABLE requests ADD COLUMN {name} {definition}')
        db.execute('CREATE INDEX IF NOT EXISTS idx_history_created ON requests(created_at DESC,id DESC)')
        # Only actual audit timestamps can backfill historical transitions.
        for field, actions in {
            'download_started_at': ('movie_download_started',),
            'available_observed_at': ('movie_available', 'tv_episode_available', 'tv_season_available'),
        }.items():
            marks = ','.join('?' for _ in actions)
            db.execute(f'''UPDATE requests SET {field}=(SELECT MIN(occurred_at) FROM audit_events
                WHERE request_id=requests.id AND action IN ({marks})) WHERE {field} IS NULL''', actions)


def utc_timestamp(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, UTC).isoformat() if value > 0 else None
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=UTC).isoformat() if parsed.tzinfo is None else parsed.astimezone(UTC).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def evidence(db, request_id, *, torrent=None, queue=None, imported_at=None):
    torrent, queue = torrent or {}, queue or {}
    size = torrent.get('total_size') or torrent.get('size') or queue.get('size')
    known = bool(('progress' in torrent and torrent['progress'] is not None) or
                 (queue.get('size') and ('sizeleft' in queue or 'sizeLeft' in queue)))
    completed = utc_timestamp(torrent.get('completion_on'))
    if not completed and str(queue.get('status') or '').lower()=='completed':
        completed = main.utc_now()  # First observed confirmed completion, not historical reconstruction.
    imported = utc_timestamp(imported_at)
    transferring = bool(float(torrent.get('dlspeed') or 0)>0) if torrent else str(queue.get('status') or '').lower()=='downloading'
    db.execute('''UPDATE requests SET
        actual_size_bytes=COALESCE(?,actual_size_bytes),
        download_completed_at=COALESCE(download_completed_at,?),
        imported_at=COALESCE(imported_at,?),
        download_started_at=CASE WHEN ? THEN COALESCE(download_started_at,?) ELSE download_started_at END,
        progress_known=CASE WHEN ? THEN 1 ELSE progress_known END WHERE id=?''',
        (int(size) if size and float(size) > 0 else None, completed, imported, transferring, main.utc_now(), known, request_id))


def history_item(row):
    item = main.public_request(dict(row))
    status = item.get('status')
    item['display_status'] = {'approved':'Requested','pending_approval':'Requested','processing':'Importing'}.get(status, str(status or 'requested').replace('_',' ').title())
    item['display_timestamp'] = (item.get('download_completed_at') or item.get('imported_at')) if status == 'available' else item.get('created_at')
    actual = item.get('actual_size_bytes')
    estimated = item.get('selected_release_size_bytes') or (float(item.get('estimated_size_gb') or 0)*1024**3 if item.get('media_type') != 'tv' else None)
    item['size_bytes'] = actual or estimated or None
    item['size_is_estimate'] = bool(not actual and estimated)
    item['display_progress'] = item.get('progress') if item.get('progress_known') and status in {'downloading','processing'} else None
    if item.get('media_type') == 'tv':
        # Older selected release titles remain authoritative if series name was never stored.
        title = item.get('series_title') or item.get('title')
        season, episode = item.get('season_number'), item.get('episode_number')
        if item.get('series_title') and season is not None:
            title += f' · S{int(season):02d}E{int(episode):02d}' if episode is not None else f' · Season {season}'
        item['display_title'] = title
    else:
        item['display_title'] = item.get('title')
    item.pop('requested_seasons_json', None)
    return item


async def refresh():
    global _last_refresh, _refresh_warning
    async with _refresh_lock:
        if monotonic()-_last_refresh < 10:
            return _refresh_warning
        try:
            # Reuse the effective reconciliation chain; never import Plex into history.
            async with asyncio.timeout(18):
                await tv_release_selection.downloads_v011(main.Principal(user_id='system', username='system', display_name='MediaHub', role='admin', active=True))
            _refresh_warning = None
        except Exception:
            _refresh_warning = 'Some integrations could not refresh. Saved request history is shown; status may be stale.'
        _last_refresh = monotonic()
    return _refresh_warning


async def history(principal: main.CurrentUser, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    initialise()
    warning = await refresh()
    with main.connect_db() as db:
        where, args = "status NOT IN ('superseded','deleted')", []
        if principal.role not in {'admin','manager'}:
            where += ' AND requested_by_id=?'
            args.append(principal.user_id)
        total = db.execute(f'SELECT COUNT(*) AS n FROM requests WHERE {where}', args).fetchone()['n']
        rows = db.execute(f'''SELECT * FROM requests WHERE {where}
            ORDER BY COALESCE(imported_at,download_completed_at,created_at) DESC,id DESC LIMIT ? OFFSET ?''',
            [*args, page_size, (page-1)*page_size]).fetchall()
    return {'items': [history_item(row) for row in rows], 'page':page, 'total_pages': max(1,(total+page_size-1)//page_size), 'total':total, 'warning':warning}
