from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Query

from . import authorized_expanded, enhanced_main, main

app = authorized_expanded.app
app.version = "0.6.9-dev"


QUALITY_RANK = {
    "1080p": 4,
    "720p": 3,
    "screener": 2,
    "telecine": 2,
    "telesync": 1,
    "cam": 1,
}

ACTIVITY_ACTIONS = {
    "movie_request_created": ("requested", "Requested"),
    "request_created": ("requested", "Requested"),
    "request_automatically_approved": ("approved", "Approved"),
    "request_pending_approval": ("pending_approval", "Pending approval"),
    "request_rejected_insufficient_storage": ("rejected", "Rejected"),
    "movie_release_grabbed": ("queued", "Queued"),
    "movie_download_started": ("downloading", "Download started"),
    "movie_available": ("available", "Available"),
    "movie_request_submission_failed": ("failed", "Failed"),
    "movie_failed": ("failed", "Failed"),
    "movie_rejected": ("rejected", "Rejected"),
    "movie_cancelled": ("cancelled", "Cancelled"),
    "movie_superseded": ("superseded", "Superseded duplicate"),
}

TRANSITION_ACTIONS = {
    "downloading": "movie_download_started",
    "failed": "movie_failed",
    "rejected": "movie_rejected",
    "cancelled": "movie_cancelled",
    "superseded": "movie_superseded",
}


def _quality_rank(release: dict[str, Any]) -> int:
    text = f"{release.get('quality', '')} {release.get('title', '')}".lower()
    for marker, rank in QUALITY_RANK.items():
        if marker in text:
            return rank
    return 0


def release_sort_key(release: dict[str, Any]) -> tuple[int, int, int, float, float]:
    """Rank actionable releases first, then preserve useful quality/health ordering."""
    eligible = bool(release.get("eligible"))
    rejected = bool(release.get("policy_rejections")) or not eligible
    usability_rank = 2 if eligible else 0 if rejected else 1
    seeders = int(release.get("seeders") or 0)
    size_gb = float(release.get("size_gb") or 0)
    age_hours = float(release.get("age_hours") or 0)
    return (
        usability_rank,
        _quality_rank(release),
        seeders,
        -size_gb,
        -age_hours,
    )


def sort_release_results(releases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(releases, key=release_sort_key, reverse=True)


async def movie_releases(
    tmdb_id: int,
    rules: main.ReleaseRules,
    principal: main.CurrentUser,
    expanded: bool = Query(default=False),
) -> dict[str, Any]:
    result = await authorized_expanded.movie_releases(
        tmdb_id,
        rules,
        principal,
        expanded=expanded,
    )
    result["releases"] = sort_release_results(list(result.get("releases") or []))
    return result


def _record_transition_once(
    db: Any,
    *,
    request_id: int,
    action: str,
    previous_status: str,
    status: str,
) -> None:
    already_recorded = db.execute(
        "SELECT 1 FROM audit_events WHERE request_id = ? AND action = ? LIMIT 1",
        (request_id, action),
    ).fetchone()
    if already_recorded:
        return
    main.record_audit(
        db,
        actor_id="system",
        actor_name="MediaHub",
        action=action,
        request_id=request_id,
        details={"previous_status": previous_status, "status": status},
    )


async def downloads(principal: main.CurrentUser) -> list[dict[str, Any]]:
    with main.connect_db() as db:
        previous = {
            int(row["id"]): str(row["status"])
            for row in db.execute(
                "SELECT id, status FROM requests WHERE media_type = 'movie'"
            ).fetchall()
        }

    results = await enhanced_main.downloads(principal)

    transitions: list[tuple[int, str, str, str]] = []
    for item in results:
        request_id = int(item.get("id") or 0)
        if not request_id:
            continue
        before = previous.get(request_id)
        after = str(item.get("status") or "")
        if before and before != after and after in TRANSITION_ACTIONS:
            transitions.append((request_id, TRANSITION_ACTIONS[after], before, after))

    if transitions:
        with main.connect_db() as db:
            for request_id, action, before, after in transitions:
                _record_transition_once(
                    db,
                    request_id=request_id,
                    action=action,
                    previous_status=before,
                    status=after,
                )
            db.commit()

    return results


def _activity_label(action: str) -> tuple[str, str] | None:
    return ACTIVITY_ACTIONS.get(action)


def _safe_reason(request: dict[str, Any], status: str) -> str | None:
    if status == "rejected":
        reason = str(request.get("rejection_reason") or "").strip()
        if reason == "insufficient_storage":
            return "Insufficient storage"
        return reason.replace("_", " ").title() if reason else None
    return None


def _user_activity_rows(db: Any, user_id: str, limit: int) -> list[dict[str, Any]]:
    requests = [
        dict(row)
        for row in db.execute(
            """
            SELECT id, media_type, title, status, rejection_reason, created_at, updated_at
            FROM requests
            WHERE requested_by_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, max(limit, 100)),
        ).fetchall()
    ]
    request_by_id = {int(item["id"]): item for item in requests}
    if not request_by_id:
        return []

    placeholders = ",".join("?" for _ in request_by_id)
    audit_rows = db.execute(
        f"""
        SELECT id, occurred_at, action, request_id, details_json
        FROM audit_events
        WHERE request_id IN ({placeholders})
        ORDER BY occurred_at DESC, id DESC
        """,
        tuple(request_by_id),
    ).fetchall()

    activity: list[dict[str, Any]] = []
    represented: set[tuple[int, str]] = set()
    for row in audit_rows:
        item = dict(row)
        request_id = int(item.get("request_id") or 0)
        request = request_by_id.get(request_id)
        if not request:
            continue
        mapped = _activity_label(str(item.get("action") or ""))
        if mapped is None:
            continue
        status, label = mapped
        represented.add((request_id, status))
        activity.append(
            {
                "request_id": request_id,
                "title": request["title"],
                "media_type": request["media_type"],
                "action": status,
                "action_label": label,
                "status": status,
                "current_status": request["status"],
                "occurred_at": item["occurred_at"],
                "reason": _safe_reason(request, status),
            }
        )

    for request in requests:
        request_id = int(request["id"])
        if (request_id, "requested") not in represented:
            activity.append(
                {
                    "request_id": request_id,
                    "title": request["title"],
                    "media_type": request["media_type"],
                    "action": "requested",
                    "action_label": "Requested",
                    "status": "requested",
                    "current_status": request["status"],
                    "occurred_at": request["created_at"],
                    "reason": None,
                }
            )

        current_status = str(request.get("status") or "")
        if current_status in {
            "downloading",
            "available",
            "failed",
            "rejected",
            "cancelled",
            "superseded",
        } and (request_id, current_status) not in represented:
            label = {
                "downloading": "Downloading",
                "available": "Available",
                "failed": "Failed",
                "rejected": "Rejected",
                "cancelled": "Cancelled",
                "superseded": "Superseded duplicate",
            }[current_status]
            activity.append(
                {
                    "request_id": request_id,
                    "title": request["title"],
                    "media_type": request["media_type"],
                    "action": current_status,
                    "action_label": label,
                    "status": current_status,
                    "current_status": current_status,
                    "occurred_at": request["updated_at"],
                    "reason": _safe_reason(request, current_status),
                }
            )

    activity.sort(
        key=lambda item: (str(item.get("occurred_at") or ""), int(item.get("request_id") or 0)),
        reverse=True,
    )
    return activity[:limit]


async def user_activity(
    user_id: str,
    _: main.Administrator,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    with main.connect_db() as db:
        user = db.execute(
            """
            SELECT id, username, display_name, role, active
            FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=404, detail="MediaHub user not found")
        activity = _user_activity_rows(db, user_id, limit)

    return {
        "user": dict(user),
        "activity": activity,
    }


# Replace only the affected routes. The existing storage, request, duplicate and
# integration logic remains authoritative in the lower layers.
enhanced_main._replace_route("/api/movies/{tmdb_id}/releases", "POST", movie_releases)
enhanced_main._replace_route("/api/downloads", "GET", downloads)
app.add_api_route(
    "/api/users/{user_id}/activity",
    user_activity,
    methods=["GET"],
)


_RELEASE_ACTIVITY_UI = r"""
<style>
  .release.rejected-release{opacity:.72;background:rgba(12,16,24,.72)}
  .release-divider{margin:10px 0 2px;padding:12px 2px 4px;color:var(--muted);font-size:.78rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em;border-top:1px solid var(--border)}
  .activity-dialog{width:min(760px,100%)}
  .activity-header{padding:26px 28px 12px}.activity-header h2{margin:0 0 6px}.activity-list{display:grid;gap:10px;padding:12px 28px 28px}
  .activity-item{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:start;padding:14px;border:1px solid var(--border);border-radius:14px;background:#0c1018}
  .activity-item h3{margin:0 0 6px;font-size:.98rem}.activity-meta{color:var(--muted);font-size:.78rem;line-height:1.5}.activity-time{color:var(--muted);font-size:.76rem;text-align:right;white-space:nowrap}
  @media(max-width:760px){.activity-header{padding:22px 20px 10px}.activity-list{padding:10px 20px 22px}.activity-item{grid-template-columns:1fr}.activity-time{text-align:left;white-space:normal}.user-controls [data-activity]{width:100%}}
</style>
<div class="modal hidden" id="activity-modal" role="dialog" aria-modal="true" aria-labelledby="activity-title">
  <div class="dialog activity-dialog">
    <button class="close" id="close-activity-modal" aria-label="Close">✕</button>
    <div class="activity-header"><div class="eyebrow">User activity</div><h2 id="activity-title">Activity</h2><div class="muted" id="activity-summary"></div></div>
    <div class="activity-list" id="activity-list"><div class="empty">Loading activity...</div></div>
  </div>
</div>
<script>
  function decorateReleaseResults(){
    const area=document.getElementById('release-area');
    if(!area)return;
    const releases=[...area.querySelectorAll('.release')];
    releases.forEach(item=>item.classList.toggle('rejected-release',!!item.querySelector('button[disabled]')));
    if(area.querySelector('.release-divider'))return;
    const firstRejected=releases.find(item=>item.querySelector('button[disabled]'));
    const hasDownloadable=releases.some(item=>item.querySelector('button:not([disabled])'));
    if(firstRejected&&hasDownloadable){
      const divider=document.createElement('div');
      divider.className='release-divider';
      divider.textContent='Other unavailable releases';
      firstRejected.before(divider);
    }
  }

  let releaseDecorationQueued=false;
  const releaseArea=document.getElementById('release-area');
  if(releaseArea){
    new MutationObserver(()=>{
      if(releaseDecorationQueued)return;
      releaseDecorationQueued=true;
      queueMicrotask(()=>{releaseDecorationQueued=false;decorateReleaseResults();});
    }).observe(releaseArea,{childList:true,subtree:true});
  }

  function formatActivityTime(value){
    const date=new Date(value);
    if(Number.isNaN(date.getTime()))return value||'';
    return date.toLocaleString(undefined,{day:'numeric',month:'short',year:'numeric',hour:'numeric',minute:'2-digit'});
  }

  function activityStatusClass(status){
    return ['available','failed','rejected'].includes(status)?status:'';
  }

  async function openUserActivity(userId){
    const modal=document.getElementById('activity-modal');
    const list=document.getElementById('activity-list');
    modal.classList.remove('hidden');
    list.innerHTML='<div class="empty">Loading activity...</div>';
    try{
      const data=await api(`users/${encodeURIComponent(userId)}/activity`);
      document.getElementById('activity-title').textContent=`${data.user.display_name} activity`;
      document.getElementById('activity-summary').textContent=`${data.activity.length} recent activity ${data.activity.length===1?'item':'items'}`;
      list.innerHTML=data.activity.length?data.activity.map(item=>`<article class="activity-item"><div><h3>${esc(item.title)}</h3><div class="activity-meta"><span class="status ${activityStatusClass(item.status)}">${esc(item.action_label)}</span> · ${esc(item.media_type)}${item.reason?`<div style="margin-top:7px">Reason: ${esc(item.reason)}</div>`:''}</div></div><div class="activity-time">${esc(formatActivityTime(item.occurred_at))}</div></article>`).join(''):'<div class="empty">No request or download activity has been recorded for this user yet.</div>';
    }catch(error){
      list.innerHTML=`<div class="empty">${esc(error.message)}</div>`;
    }
  }

  function addActivityButtons(){
    document.querySelectorAll('#user-list [data-user-id]').forEach(card=>{
      if(card.querySelector('[data-activity]'))return;
      const controls=card.querySelector('.user-controls');
      if(!controls)return;
      const button=document.createElement('button');
      button.className='button';
      button.type='button';
      button.dataset.activity='';
      button.textContent='View activity';
      button.addEventListener('click',()=>openUserActivity(card.dataset.userId));
      controls.prepend(button);
    });
  }

  const userList=document.getElementById('user-list');
  if(userList){
    new MutationObserver(addActivityButtons).observe(userList,{childList:true,subtree:true});
    addActivityButtons();
  }

  document.getElementById('close-activity-modal').addEventListener('click',()=>document.getElementById('activity-modal').classList.add('hidden'));
  document.getElementById('activity-modal').addEventListener('click',event=>{if(event.target.id==='activity-modal')event.currentTarget.classList.add('hidden');});
</script>
"""

if "id=\"activity-modal\"" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _RELEASE_ACTIVITY_UI + "\n</body>")
