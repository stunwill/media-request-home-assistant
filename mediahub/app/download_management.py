"""Bounded, permission-scoped presentation of immutable acquisition attempts."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Literal

from fastapi import HTTPException, Query

from . import download_history as history, main
from .schema_migrations import serialised

TERMINAL = {'failed', 'rejected', 'cancelled', 'timed_out'}
GROUP = """CASE WHEN COALESCE(external_id,'')='' THEN 'request:'||id ELSE
 media_type||':'||external_id||':'||COALESCE(requested_scope,'movie')||':'||
 COALESCE(season_number,'')||':'||COALESCE(episode_number,'')||':'||
 COALESCE(requested_seasons_json,'') END"""
SORTS = {'newest':'created_at DESC,id DESC', 'oldest':'created_at ASC,id ASC',
         'title':'title COLLATE NOCASE,id DESC', 'requester':'requested_by_name COLLATE NOCASE,id DESC',
         'type':'media_type,id DESC', 'status':'status,id DESC'}


def safe_text(value):
    text = str(value or '')
    text = re.sub(r'https?://\S+', '[URL withheld]', text, flags=re.I)
    text = re.sub(r'(?i)(api[_-]?key|authorization|token|password)\s*[:=]\s*[^\s,;]+', r'\1=[redacted]', text)
    return text[:1500]


@serialised
def initialise():
    with main.connect_db() as db:
        columns = {row['name'] for row in db.execute('PRAGMA table_info(requests)')}
        for name, definition in {'selected_release_quality':'TEXT', 'selected_release_seeders':'INTEGER',
                                 'sent_at':'TEXT', 'failure_json':'TEXT'}.items():
            if name not in columns:
                db.execute(f'ALTER TABLE requests ADD COLUMN {name} {definition}')
        db.execute('CREATE INDEX IF NOT EXISTS idx_history_identity ON requests(media_type,external_id,created_at,id)')
        # Audit evidence only. Never updated_at or now() for historical handoffs.
        db.execute("""UPDATE requests SET sent_at=(SELECT MIN(occurred_at) FROM audit_events
          WHERE request_id=requests.id AND action IN ('movie_release_grabbed','tv_episode_release_selected','tv_season_release_selected'))
          WHERE sent_at IS NULL""")
        for field,path in [('selected_release_quality','$.release.quality'),('selected_release_source','$.release.indexer')]:
            db.execute(f'''UPDATE requests SET {field}=(SELECT json_extract(details_json,?) FROM audit_events
              WHERE request_id=requests.id AND json_valid(details_json) AND json_extract(details_json,?) IS NOT NULL
              ORDER BY occurred_at LIMIT 1) WHERE {field} IS NULL''',(path,path))


def visibility(principal):
    return ("status NOT IN ('superseded','deleted')", []) if principal.role in {'admin','manager'} else (
        "status NOT IN ('superseded','deleted') AND requested_by_id=?", [principal.user_id])


def failure(item):
    if item.get('status') not in TERMINAL:
        return None
    if item.get('failure_json'):
        try:
            recorded = json.loads(item['failure_json'])
            return {key:safe_text(recorded[key]) for key in ('integration','category','explanation','timestamp','response_code') if recorded.get(key) is not None}
        except (ValueError, TypeError):
            pass
    # Do not infer response codes/timestamps that were not recorded.
    explanation = safe_text(item.get('status_message') or item.get('rejection_reason'))
    integration = 'Radarr' if 'radarr' in explanation.lower() else 'Sonarr' if 'sonarr' in explanation.lower() else 'MediaHub'
    return {'integration':integration, 'category':item['status'], 'explanation':explanation,
            'retry': 'Review current releases and settings before a new attempt.'}


def present(row):
    item = history.history_item(row)
    item['failure'] = failure(item)
    item.pop('failure_json', None)
    for name in ('status_message','rejection_reason','selected_release_title','selected_release_source'):
        if item.get(name):
            item[name] = safe_text(item[name])
    status = item.get('status')
    item['lifecycle'] = {
        'manager': 'Accepted' if item.get('sent_at') or status in {'queued','downloading','processing','available'} else 'Not confirmed',
        'client': 'Transfer completed' if item.get('download_completed_at') else 'Downloading' if status=='downloading' else 'Not confirmed',
        'import': 'Imported' if item.get('imported_at') else 'Not confirmed',
        'library': 'Verified in media manager library' if status=='available' else 'Not confirmed',
    }
    # Retry is a fresh discovery review, never an automatic repeat of a rejected token.
    item['retry_supported'] = status in TERMINAL and item.get('media_type')=='movie' and str(item.get('external_id') or '').isdigit()
    return item


async def listing(principal: main.CurrentUser, page: int=Query(1,ge=1), page_size: int=Query(30,ge=1,le=100),
                  sort: Literal['newest','oldest','title','requester','type','status']='newest',
                  media: Literal['all','movie','tv']='all', requester: str=Query('',max_length=250),
                  status: Literal['all','completed','downloading','failed','available']='all', refresh: bool=True):
    warning = await history.refresh() if refresh else None
    return await asyncio.to_thread(query_groups,principal,page,page_size,sort,media,requester,status,warning)


def query_groups(principal,page,page_size,sort,media,requester,status,warning=None):
    where,args = visibility(principal)
    # Group before filters: latest attempt defines the group, previous attempts remain reachable.
    cte=f'''WITH visible AS (SELECT *,{GROUP} group_key FROM requests WHERE {where}),
      ranked AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY group_key ORDER BY created_at DESC,id DESC) position,
       COUNT(*) OVER(PARTITION BY group_key) attempt_count FROM visible)'''
    selected=['position=1']
    if media!='all':
        selected.append('media_type=?'); args.append(media)
    if requester:
        selected.append('requested_by_id=?'); args.append(requester)
    statuses={'completed':('processing','available'), 'downloading':('downloading',),
              'failed':('failed','rejected','timed_out','cancelled'), 'available':('available',)}
    if status in statuses:
        values=statuses[status]
        if status=='completed':
            selected.append("(download_completed_at IS NOT NULL OR imported_at IS NOT NULL)")
        else:
            selected.append('status IN ('+','.join('?' for _ in values)+')'); args.extend(values)
    clause=' AND '.join(selected)
    with main.connect_db() as db:
        total=db.execute(cte+f' SELECT COUNT(*) n FROM ranked WHERE {clause}',args).fetchone()['n']
        rows=db.execute(cte+f' SELECT * FROM ranked WHERE {clause} ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?',
                        [*args,page_size,(page-1)*page_size]).fetchall()
        user_where,user_args=visibility(principal)
        users=db.execute(f'''SELECT DISTINCT requested_by_id id,requested_by_name name FROM requests
          WHERE {user_where} ORDER BY name COLLATE NOCASE''',user_args).fetchall()
    return {'items':[present(row) for row in rows],'page':page,'total':total,
            'total_pages':max(1,(total+page_size-1)//page_size), 'requesters':[dict(row) for row in users],
            'warning':warning, 'scope':'Latest attempt per stable media identity; expand for earlier attempts.'}


async def attempts(request_id: int, principal: main.CurrentUser, page: int=Query(1,ge=1)):
    where,args=visibility(principal)
    with main.connect_db() as db:
        target=db.execute(f'SELECT {GROUP} group_key FROM requests WHERE id=? AND {where}',[request_id,*args]).fetchone()
        if not target:
            raise HTTPException(404,'Request not found.')
        group=target['group_key']
        total=db.execute(f'SELECT COUNT(*) n FROM requests WHERE {where} AND ({GROUP})=?',[*args,group]).fetchone()['n']
        rows=db.execute(f'''SELECT * FROM requests WHERE {where} AND ({GROUP})=?
          ORDER BY created_at DESC,id DESC LIMIT 20 OFFSET ?''',[*args,group,(page-1)*20]).fetchall()
    return {'items':[present(row) for row in rows],'page':page,'total':total,'total_pages':max(1,(total+19)//20)}
