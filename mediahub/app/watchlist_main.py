from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from . import main, mobile_ux_ui, preset_main, release_lifecycle, runtime

app = mobile_ux_ui.app
app.version = "0.15.1-dev"
logger = logging.getLogger("mediahub.watchlist")


class WatchlistCreate(BaseModel):
    """The server owns release policy. Clients only identify the movie."""



def initialise_watchlist_database() -> None:
    release_lifecycle.initialise_watch_database()
    with main.connect_db() as db:
        columns = {str(row["name"]) for row in db.execute("PRAGMA table_info(movie_watches)").fetchall()}
        migrations = {
            "poster_path": "TEXT",
            "availability_state": "TEXT NOT NULL DEFAULT 'waiting'",
            "first_available_at": "TEXT",
            "notification_sent_at": "TEXT",
        }
        for name, definition in migrations.items():
            if name not in columns:
                db.execute(f"ALTER TABLE movie_watches ADD COLUMN {name} {definition}")
        db.execute("CREATE INDEX IF NOT EXISTS idx_movie_watches_owner ON movie_watches (requested_by_id, created_at)")
        db.commit()


def _availability(lifecycle_state: str, *, found: bool, request_status: str | None = None) -> str:
    if request_status == "available":
        return "downloaded"
    if request_status in {"approved", "searching", "queued", "downloading", "processing"}:
        return "downloading"
    if found:
        return "available"
    if lifecycle_state in {"announced", "theatrical_upcoming"}:
        return "upcoming"
    if lifecycle_state in {"in_cinemas", "digital_upcoming", "physical_upcoming"}:
        return "waiting"
    return "no_eligible_release"


def _public_watch(row: dict[str, Any], request_status: str | None = None) -> dict[str, Any]:
    found = bool(row.get("qualifying_release_found"))
    availability = _availability(str(row.get("lifecycle_state") or "released_unknown"), found=found, request_status=request_status)
    return {
        "id": int(row["id"]),
        "tmdb_id": int(row["tmdb_id"]),
        "title": row["title"],
        "year": row.get("year"),
        "poster_path": row.get("poster_path"),
        "owner_id": row["requested_by_id"],
        "owner_name": row["requested_by_name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "lifecycle_state": row["lifecycle_state"],
        "theatrical_date": row.get("theatrical_date"),
        "digital_date": row.get("digital_date"),
        "physical_date": row.get("physical_date"),
        "last_checked_at": row.get("last_checked_at"),
        "next_check_at": row.get("next_check_at"),
        "qualifying_release_found": found,
        "first_available_at": row.get("first_available_at"),
        "availability_state": availability,
        "request_id": row.get("request_id"),
        "request_status": request_status,
    }


def _request_status(db: Any, tmdb_id: int, user_id: str) -> tuple[str | None, int | None]:
    row = db.execute(
        """
        SELECT id, status FROM requests
        WHERE media_type='movie' AND external_id=? AND requested_by_id=?
        ORDER BY created_at DESC, id DESC LIMIT 1
        """,
        (str(tmdb_id), user_id),
    ).fetchone()
    return (str(row["status"]), int(row["id"])) if row else (None, None)


async def add_to_watchlist(tmdb_id: int, _payload: WatchlistCreate, principal: main.CurrentUser) -> dict[str, Any]:
    initialise_watchlist_database()
    tmdb, _, _ = main.configured_clients(main.load_options())
    try:
        movie = await tmdb.details(tmdb_id)
    except runtime.media_services.MediaServiceError as error:
        raise main.service_http_error(error) from error
    lifecycle = release_lifecycle.classify_movie(movie)
    now = datetime.now(UTC)
    rules = preset_main.movie_rules()
    due = release_lifecycle.next_check(lifecycle, now=now).isoformat()
    poster = movie.get("poster_path") or movie.get("poster_url")
    with main.connect_db() as db:
        existing = release_lifecycle._watch_row(db, tmdb_id, principal.user_id)
        if existing:
            request_status, _ = _request_status(db, tmdb_id, principal.user_id)
            return _public_watch(existing, request_status)
        db.execute(
            """
            INSERT INTO movie_watches (
                tmdb_id,title,year,requested_by_id,requested_by_name,created_at,updated_at,
                lifecycle_state,region,theatrical_date,digital_date,physical_date,next_check_at,
                maximum_size_gb,minimum_seeders,quality_mode,status,poster_path,availability_state
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'watching',?,?)
            """,
            (
                tmdb_id, movie["title"], int(movie["year"]) if str(movie.get("year") or "").isdigit() else None,
                principal.user_id, principal.display_name, now.isoformat(), now.isoformat(), lifecycle["state"],
                lifecycle["region"], lifecycle["theatrical_date"], lifecycle["digital_date"], lifecycle["physical_date"],
                due, rules.maximum_size_gb, rules.minimum_seeders, rules.quality_mode, poster,
                _availability(lifecycle["state"], found=False),
            ),
        )
        main.record_audit(db, actor_id=principal.user_id, actor_name=principal.display_name,
                          action="movie_watch_created", request_id=None,
                          details={"tmdb_id": tmdb_id, "lifecycle_state": lifecycle["state"], "next_check_at": due})
        db.commit()
        row = release_lifecycle._watch_row(db, tmdb_id, principal.user_id)
    return _public_watch(row or {})


async def list_watchlist(principal: main.CurrentUser) -> list[dict[str, Any]]:
    initialise_watchlist_database()
    with main.connect_db() as db:
        rows = [dict(row) for row in db.execute(
            "SELECT * FROM movie_watches WHERE requested_by_id=? ORDER BY created_at DESC, id DESC",
            (principal.user_id,),
        ).fetchall()]
        result = []
        for row in rows:
            request_status, request_id = _request_status(db, int(row["tmdb_id"]), principal.user_id)
            if request_id and row.get("request_id") != request_id:
                row["request_id"] = request_id
            result.append(_public_watch(row, request_status))
    return result


async def remove_from_watchlist(tmdb_id: int, principal: main.CurrentUser) -> dict[str, bool]:
    initialise_watchlist_database()
    with main.connect_db() as db:
        row = release_lifecycle._watch_row(db, tmdb_id, principal.user_id)
        if not row:
            raise HTTPException(status_code=404, detail="Movie is not on your Watchlist")
        db.execute("DELETE FROM movie_watches WHERE id=?", (row["id"],))
        main.record_audit(db, actor_id=principal.user_id, actor_name=principal.display_name,
                          action="movie_watch_removed", request_id=None, details={"tmdb_id": tmdb_id})
        db.commit()
    return {"removed": True}


async def _evaluate_watch(row: dict[str, Any], *, manual: bool = False) -> dict[str, Any]:
    tmdb_id = int(row["tmdb_id"])
    tmdb, _, _ = main.configured_clients(main.load_options())
    movie = await tmdb.details(tmdb_id)
    lifecycle = release_lifecycle.classify_movie(movie)
    now = datetime.now(UTC)
    rules = preset_main.movie_rules()
    found = False
    search_state = "deferred_upcoming"
    release_count = 0
    eligible_count = 0
    if manual or lifecycle["state"] not in {"announced", "theatrical_upcoming"}:
        _, releases, _ = await runtime.search_movie_releases(tmdb_id, rules, str(row["requested_by_id"]), movie=movie)
        release_count = len(releases)
        eligible_count = sum(1 for item in releases if item.get("eligible"))
        found = eligible_count > 0
        search_state = "available" if found else ("no_eligible_release" if releases else "no_results")
    due = release_lifecycle.next_check(lifecycle, now=now)
    poster = movie.get("poster_path") or movie.get("poster_url") or row.get("poster_path")
    first_available = row.get("first_available_at") or (now.isoformat() if found else None)
    availability = _availability(lifecycle["state"], found=found)
    with main.connect_db() as db:
        db.execute(
            """
            UPDATE movie_watches SET title=?,year=?,poster_path=?,lifecycle_state=?,theatrical_date=?,digital_date=?,physical_date=?,
                last_checked_at=?,next_check_at=?,maximum_size_gb=?,minimum_seeders=?,quality_mode=?,qualifying_release_found=?,
                first_available_at=?,availability_state=?,status=?,updated_at=? WHERE id=?
            """,
            (movie["title"], int(movie["year"]) if str(movie.get("year") or "").isdigit() else None, poster,
             lifecycle["state"], lifecycle["theatrical_date"], lifecycle["digital_date"], lifecycle["physical_date"],
             now.isoformat(), due.isoformat(), rules.maximum_size_gb, rules.minimum_seeders, rules.quality_mode,
             1 if found else 0, first_available, availability, "release_found" if found else "watching", now.isoformat(), row["id"]),
        )
        if found and not row.get("qualifying_release_found"):
            main.record_audit(db, actor_id="system", actor_name="MediaHub", action="movie_watch_release_found",
                              request_id=None, details={"tmdb_id": tmdb_id, "watch_id": row["id"]})
        db.commit()
        updated = release_lifecycle._watch_row(db, tmdb_id, str(row["requested_by_id"]))
    result = _public_watch(updated or {})
    result.update({"search_state": search_state, "release_count": release_count, "eligible_count": eligible_count})
    return result


async def refresh_watch(tmdb_id: int, principal: main.CurrentUser) -> dict[str, Any]:
    initialise_watchlist_database()
    with main.connect_db() as db:
        row = release_lifecycle._watch_row(db, tmdb_id, principal.user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Movie is not on your Watchlist")
    try:
        return await _evaluate_watch(row, manual=True)
    except runtime.media_services.MediaServiceError as error:
        raise main.service_http_error(error) from error
    except Exception as error:
        logger.exception("manual Watchlist refresh failed tmdb_id=%s", tmdb_id)
        raise HTTPException(status_code=503, detail="Release check failed temporarily. Your Watchlist state was not changed.") from error


async def process_due_watches() -> None:
    now = datetime.now(UTC)
    initialise_watchlist_database()
    with main.connect_db() as db:
        rows = [dict(row) for row in db.execute(
            "SELECT * FROM movie_watches WHERE status='watching' AND next_check_at<=? ORDER BY next_check_at LIMIT 20",
            (now.isoformat(),),
        ).fetchall()]
    for row in rows:
        try:
            await _evaluate_watch(row, manual=False)
        except Exception:
            # Preserve the last known state on provider/network failure. The existing due time
            # remains eligible for a later cycle instead of falsely marking the movie unavailable.
            logger.exception("automatic Watchlist check failed tmdb_id=%s", row.get("tmdb_id"))
        await asyncio.sleep(1)


# Upgrade the existing release-lifecycle watcher rather than running a second poller.
release_lifecycle.process_due_watches = process_due_watches
runtime.enhanced_main._replace_route("/api/movies/{tmdb_id}/watch", "POST", add_to_watchlist)
app.add_api_route("/api/watchlist", list_watchlist, methods=["GET"])
app.add_api_route("/api/watchlist/{tmdb_id}", remove_from_watchlist, methods=["DELETE"])
app.add_api_route("/api/watchlist/{tmdb_id}/refresh", refresh_watch, methods=["POST"])


@app.on_event("startup")
def watchlist_startup() -> None:
    initialise_watchlist_database()


_WATCHLIST_UI = r"""
<style>
.watchlist-toolbar{display:flex;gap:8px;overflow:auto;margin:0 0 18px}.watchlist-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:18px}.watch-card{border:1px solid var(--border);border-radius:16px;background:var(--surface);overflow:hidden;min-width:0}.watch-poster{aspect-ratio:2/3;background:#111620;cursor:pointer}.watch-poster img{width:100%;height:100%;object-fit:cover}.watch-copy{padding:12px}.watch-copy h3{font-size:.95rem;margin:0 0 5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.watch-state{display:inline-flex;margin:7px 0;padding:5px 8px;border-radius:99px;background:#252b38;color:#c8d0dd;font-size:.68rem;font-weight:900;text-transform:uppercase}.watch-state.available{background:rgba(58,214,140,.12);color:var(--success)}.watch-state.upcoming{background:rgba(255,198,90,.12);color:var(--warning)}.watch-actions{display:flex;gap:7px;margin-top:10px}.watch-actions .button{flex:1;padding:8px;font-size:.75rem}.watch-date{font-size:.74rem;color:var(--muted);line-height:1.45}.watchlist-detail-action{margin-top:8px}
@media(max-width:760px){.watchlist-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.watch-copy{padding:10px}.watch-actions{flex-direction:column}.watchlist-toolbar{margin-top:8px}.watchlist-toolbar .chip{flex:0 0 auto}}
</style>
<script>
(function(){
 if(window.MEDIAHUB_WATCHLIST_V0150)return;window.MEDIAHUB_WATCHLIST_V0150=true;
 const shell=document.querySelector('main.shell');if(!shell)return;
 const section=document.createElement('section');section.id='watchlist-view';section.className='hidden';section.innerHTML='<div class="heading"><div><h2>Watchlist</h2><p>Upcoming and unavailable movies MediaHub is monitoring for you.</p></div></div><div class="watchlist-toolbar" id="watchlist-filters"><button class="chip active" data-watch-filter="all">All</button><button class="chip" data-watch-filter="upcoming">Upcoming</button><button class="chip" data-watch-filter="waiting">Waiting</button><button class="chip" data-watch-filter="available">Available</button></div><div id="watchlist-grid" class="watchlist-grid"><div class="empty">Loading Watchlist...</div></div>';shell.appendChild(section);
 let watchFilter='all',watchItems=[];
 const desktopNav=document.querySelector('.topbar nav');if(desktopNav&&!desktopNav.querySelector('[data-view="watchlist"]')){const b=document.createElement('button');b.dataset.view='watchlist';b.textContent='Watchlist';desktopNav.querySelector('[data-view="downloads"]')?.after(b);b.addEventListener('click',showWatchlist);}
 const mobileNav=document.querySelector('.mobile-bottom-nav');if(mobileNav&&!mobileNav.querySelector('[data-view="watchlist"]')){const b=document.createElement('button');b.dataset.view='watchlist';b.textContent='Watchlist';mobileNav.querySelector('[data-view="downloads"]')?.after(b);b.addEventListener('click',showWatchlist);}
 function showWatchlist(){document.querySelectorAll('main.shell>section').forEach(s=>s.classList.toggle('hidden',s.id!=='watchlist-view'));document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view==='watchlist'));loadWatchlist();window.scrollTo({top:0,behavior:'instant'});}
 document.addEventListener('click',e=>{const v=e.target.closest('[data-view]');if(v&&v.dataset.view!=='watchlist')section.classList.add('hidden');},true);
 function label(s){return({upcoming:'Upcoming',waiting:'Awaiting release',no_eligible_release:'No eligible release',available:'Available',downloading:'Downloading',downloaded:'Downloaded'})[s]||s.replaceAll('_',' ')}
 function poster(item){const p=item.poster_path||'';if(!p)return '<div class="no-poster">No poster</div>';const src=p.startsWith('http')?p:`https://image.tmdb.org/t/p/w500${p}`;return `<img src="${esc(src)}" alt="${esc(item.title)} poster" loading="lazy">`;}
 function dateLine(item){if(item.digital_date)return `Digital: ${esc(item.digital_date)}`;if(item.theatrical_date)return `Cinema: ${esc(item.theatrical_date)}`;return 'Digital release date not announced';}
 function renderWatchlist(){const visible=watchItems.filter(i=>watchFilter==='all'||(watchFilter==='waiting'&&['waiting','no_eligible_release'].includes(i.availability_state))||i.availability_state===watchFilter);const grid=document.getElementById('watchlist-grid');grid.innerHTML=visible.length?visible.map(i=>`<article class="watch-card" data-watch-id="${i.tmdb_id}"><div class="watch-poster" role="button" tabindex="0" aria-label="Open ${esc(i.title)}">${poster(i)}</div><div class="watch-copy"><h3>${esc(i.title)}</h3><div class="muted">${esc(i.year||'')}</div><span class="watch-state ${esc(i.availability_state)}">${esc(label(i.availability_state))}</span><div class="watch-date">${dateLine(i)}${i.last_checked_at?`<br>Checked ${esc(new Date(i.last_checked_at).toLocaleString())}`:''}</div><div class="watch-actions"><button class="button" data-watch-refresh>Check now</button><button class="button danger" data-watch-remove>Remove</button></div></div></article>`).join(''):'<div class="empty">No movies match this Watchlist filter.</div>';grid.querySelectorAll('.watch-card').forEach(card=>{const id=Number(card.dataset.watchId);const open=()=>window.openMovie?.(id,card);card.querySelector('.watch-poster')?.addEventListener('click',open);card.querySelector('.watch-poster')?.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});card.querySelector('[data-watch-refresh]')?.addEventListener('click',()=>refreshWatch(id,card));card.querySelector('[data-watch-remove]')?.addEventListener('click',()=>removeWatch(id));});}
 async function loadWatchlist(){const grid=document.getElementById('watchlist-grid');try{watchItems=await api('watchlist');renderWatchlist();}catch(error){grid.innerHTML=`<div class="empty">${esc(error.message)}</div>`;}}
 async function refreshWatch(id,card){const b=card.querySelector('[data-watch-refresh]');b.disabled=true;b.textContent='Checking...';try{const updated=await api(`watchlist/${id}/refresh`,{method:'POST'});watchItems=watchItems.map(i=>i.tmdb_id===id?{...i,...updated}:i);renderWatchlist();toast(updated.availability_state==='available'?'Release available to download.':'No eligible release found yet.');}catch(error){toast(error.message);b.disabled=false;b.textContent='Check now';}}
 async function removeWatch(id){try{await api(`watchlist/${id}`,{method:'DELETE'});watchItems=watchItems.filter(i=>i.tmdb_id!==id);if(window.state?.movie?.tmdb_id===id){window.state.movie.watch=null;decorateDetail();}renderWatchlist();toast('Removed from Watchlist.');}catch(error){toast(error.message);}}
 document.getElementById('watchlist-filters').addEventListener('click',e=>{const b=e.target.closest('[data-watch-filter]');if(!b)return;watchFilter=b.dataset.watchFilter;document.querySelectorAll('[data-watch-filter]').forEach(x=>x.classList.toggle('active',x===b));renderWatchlist();});
 function decorateDetail(){const movie=window.state?.movie;if(!movie||movie.context==='downloads')return;const actions=document.querySelector('#detail .actions');if(!actions)return;let b=document.getElementById('watchlist-toggle');document.getElementById('watch-release')?.remove();if(!b){b=document.createElement('button');b.id='watchlist-toggle';b.className='button watchlist-detail-action';actions.appendChild(b);}b.textContent=movie.watch?'Remove from Watchlist':'Add to Watchlist';b.classList.toggle('danger',!!movie.watch);b.onclick=async()=>{b.disabled=true;try{if(movie.watch){await api(`watchlist/${movie.tmdb_id}`,{method:'DELETE'});movie.watch=null;toast('Removed from Watchlist.');}else{movie.watch=await api(`movies/${movie.tmdb_id}/watch`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});toast('Added to Watchlist. MediaHub will keep checking for eligible releases.');}decorateDetail();}catch(error){toast(error.message);b.disabled=false;}};}
 const originalRender=window.renderDetail;if(typeof originalRender==='function')window.renderDetail=function(){const r=originalRender.apply(this,arguments);decorateDetail();return r;};
 const observer=new MutationObserver(()=>{if(!document.getElementById('modal')?.classList.contains('hidden'))decorateDetail();});observer.observe(document.getElementById('detail')||document.body,{childList:true,subtree:false});
})();
</script>
"""

if "MEDIAHUB_WATCHLIST_V0150" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _WATCHLIST_UI + "\n</body>")
