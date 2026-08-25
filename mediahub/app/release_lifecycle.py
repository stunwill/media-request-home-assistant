from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import HTTPException, Query
from pydantic import BaseModel

from . import dual_login, main, release_activity, runtime

app = dual_login.app
app.version = "0.7.0-dev"
logger = logging.getLogger("mediahub.release_lifecycle")

DEFAULT_REGION = "AU"
LifecycleState = Literal[
    "announced",
    "theatrical_upcoming",
    "in_cinemas",
    "digital_upcoming",
    "digital_available",
    "physical_upcoming",
    "physical_available",
    "released_unknown",
]


class WatchCreate(main.ReleaseRules):
    pass


def _today() -> date:
    return date.today()


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _display_date(value: date | None) -> str | None:
    return value.strftime("%-d %B %Y") if value else None


def _regional_release_dates(movie: dict[str, Any], region: str) -> list[dict[str, Any]]:
    countries = movie.get("release_dates") or {}
    if isinstance(countries, dict):
        values = countries.get(region) or []
        return [item for item in values if isinstance(item, dict)]
    return []


def _first_type(records: list[dict[str, Any]], types: set[int]) -> date | None:
    dates = sorted(
        parsed
        for item in records
        if int(item.get("type") or 0) in types
        if (parsed := _parse_date(item.get("release_date"))) is not None
    )
    return dates[0] if dates else None


def classify_movie(
    movie: dict[str, Any],
    *,
    region: str = DEFAULT_REGION,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or _today()
    regional = _regional_release_dates(movie, region)
    theatrical = _first_type(regional, {2, 3}) or _parse_date(movie.get("release_date"))
    digital = _first_type(regional, {4})
    physical = _first_type(regional, {5})

    if digital and digital <= today:
        state: LifecycleState = "digital_available"
    elif physical and physical <= today:
        state = "physical_available"
    elif digital and digital > today:
        state = "digital_upcoming"
    elif physical and physical > today and theatrical and theatrical <= today:
        state = "physical_upcoming"
    elif theatrical and theatrical > today:
        state = "theatrical_upcoming"
    elif theatrical and theatrical <= today:
        state = "in_cinemas" if (today - theatrical).days <= 90 else "released_unknown"
    elif movie.get("status") in {"Planned", "In Production", "Post Production"}:
        state = "announced"
    else:
        state = "released_unknown"

    lifecycle = {
        "state": state,
        "region": region,
        "theatrical_date": _iso(theatrical),
        "digital_date": _iso(digital),
        "physical_date": _iso(physical),
        "theatrical_display": _display_date(theatrical),
        "digital_display": _display_date(digital),
        "physical_display": _display_date(physical),
        "media_available": state in {"digital_available", "physical_available"},
    }
    logger.info(
        "movie lifecycle classified tmdb_id=%s region=%s state=%s theatrical=%s digital=%s physical=%s",
        movie.get("tmdb_id"), region, state, lifecycle["theatrical_date"], lifecycle["digital_date"], lifecycle["physical_date"],
    )
    return lifecycle


def lifecycle_message(lifecycle: dict[str, Any], *, today: date | None = None) -> dict[str, str]:
    today = today or _today()
    state = lifecycle["state"]
    theatrical = _parse_date(lifecycle.get("theatrical_date"))
    digital = _parse_date(lifecycle.get("digital_date"))
    if state == "announced":
        return {"label": "ANNOUNCED", "headline": "Release date not announced", "explanation": "No downloadable release is expected yet. MediaHub can watch for an appropriate release."}
    if state == "theatrical_upcoming":
        headline = f"In Australian cinemas {lifecycle['theatrical_display']}" if lifecycle.get("theatrical_display") else "Theatrical release upcoming"
        return {"label": "UPCOMING", "headline": headline, "explanation": "No downloadable release is expected yet. MediaHub can watch for an appropriate release when one becomes available."}
    if state == "in_cinemas":
        if theatrical:
            days = (today - theatrical).days
            headline = "Now in cinemas" if days <= 14 else f"Released in cinemas {days // 7} weeks ago"
        else:
            headline = "Now in cinemas"
        return {"label": "IN CINEMAS", "headline": headline, "explanation": "A theatrical release does not necessarily mean a digital copy is available yet."}
    if state == "digital_upcoming":
        return {"label": "DIGITAL SOON", "headline": f"Digital release {lifecycle['digital_display']}", "explanation": "MediaHub can watch for a qualifying release and increase search frequency as the digital date approaches."}
    if state == "digital_available":
        return {"label": "DIGITAL AVAILABLE", "headline": f"Digital release reached {lifecycle['digital_display']}", "explanation": "Normal MediaHub release search is available."}
    if state == "physical_upcoming":
        return {"label": "PHYSICAL SOON", "headline": f"Physical release {lifecycle['physical_display']}", "explanation": "MediaHub can continue watching for a preferred release."}
    if state == "physical_available":
        return {"label": "PHYSICAL AVAILABLE", "headline": f"Physical release reached {lifecycle['physical_display']}", "explanation": "Normal MediaHub release search is available."}
    return {"label": "RELEASED", "headline": "Release availability uncertain", "explanation": "MediaHub can search your configured sources now."}


def next_check(lifecycle: dict[str, Any], *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    today = now.date()
    state = lifecycle["state"]
    theatrical = _parse_date(lifecycle.get("theatrical_date"))
    digital = _parse_date(lifecycle.get("digital_date"))
    if state == "announced":
        return now + timedelta(days=14)
    if state == "theatrical_upcoming" and theatrical:
        days = (theatrical - today).days
        if days > 60:
            return now + timedelta(days=14)
        if days > 14:
            return now + timedelta(days=7)
        return now + timedelta(days=2)
    if state == "digital_upcoming" and digital:
        days = (digital - today).days
        if days > 30:
            return now + timedelta(days=7)
        if days > 7:
            return now + timedelta(days=2)
        return now + timedelta(hours=12)
    if state == "in_cinemas":
        return now + timedelta(days=2)
    if state in {"digital_available", "physical_available", "released_unknown", "physical_upcoming"}:
        return now + timedelta(hours=12)
    return now + timedelta(days=7)


def initialise_watch_database() -> None:
    main.DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with main.connect_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS movie_watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                year INTEGER,
                requested_by_id TEXT NOT NULL,
                requested_by_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                lifecycle_state TEXT NOT NULL,
                region TEXT NOT NULL,
                theatrical_date TEXT,
                digital_date TEXT,
                physical_date TEXT,
                last_checked_at TEXT,
                next_check_at TEXT NOT NULL,
                maximum_size_gb REAL NOT NULL DEFAULT 3,
                minimum_seeders INTEGER NOT NULL DEFAULT 1,
                quality_mode TEXT NOT NULL DEFAULT '720p_and_1080p',
                qualifying_release_found INTEGER NOT NULL DEFAULT 0,
                request_id INTEGER,
                status TEXT NOT NULL DEFAULT 'watching',
                UNIQUE (tmdb_id, requested_by_id)
            );
            CREATE INDEX IF NOT EXISTS idx_movie_watches_due
            ON movie_watches (status, next_check_at, tmdb_id);
            """
        )
        db.commit()


def _watch_row(db: Any, tmdb_id: int, user_id: str) -> dict[str, Any] | None:
    try:
        row = db.execute(
            "SELECT * FROM movie_watches WHERE tmdb_id = ? AND requested_by_id = ? LIMIT 1",
            (tmdb_id, user_id),
        ).fetchone()
    except Exception as error:
        if "no such table: movie_watches" not in str(error):
            raise
        initialise_watch_database()
        row = db.execute(
            "SELECT * FROM movie_watches WHERE tmdb_id = ? AND requested_by_id = ? LIMIT 1",
            (tmdb_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def _watch_public(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "tmdb_id": row["tmdb_id"],
        "status": row["status"],
        "lifecycle_state": row["lifecycle_state"],
        "next_check_at": row["next_check_at"],
        "last_checked_at": row["last_checked_at"],
        "qualifying_release_found": bool(row["qualifying_release_found"]),
        "request_id": row["request_id"],
    }


async def movie_details(tmdb_id: int, principal: main.CurrentUser) -> dict[str, Any]:
    tmdb, _, _ = main.configured_clients(main.load_options())
    try:
        movie = await tmdb.details(tmdb_id)
    except runtime.media_services.MediaServiceError as error:
        raise main.service_http_error(error) from error
    lifecycle = classify_movie(movie)
    movie["lifecycle"] = lifecycle
    movie["lifecycle_message"] = lifecycle_message(lifecycle)
    movie["digital_release_label"] = lifecycle["digital_display"] or "Digital release date not announced"
    initialise_watch_database()
    with main.connect_db() as db:
        movie["watch"] = _watch_public(_watch_row(db, tmdb_id, principal.user_id))
    return movie


async def watch_movie(
    tmdb_id: int,
    payload: WatchCreate,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    movie = await movie_details(tmdb_id, principal)
    lifecycle = movie["lifecycle"]
    now = datetime.now(UTC)
    with main.connect_db() as db:
        existing = _watch_row(db, tmdb_id, principal.user_id)
        if existing:
            logger.info("watcher already exists tmdb_id=%s user_id=%s", tmdb_id, principal.user_id)
            return _watch_public(existing) or {}
        due = next_check(lifecycle, now=now).isoformat()
        db.execute(
            """
            INSERT INTO movie_watches (
                tmdb_id,title,year,requested_by_id,requested_by_name,created_at,updated_at,
                lifecycle_state,region,theatrical_date,digital_date,physical_date,next_check_at,
                maximum_size_gb,minimum_seeders,quality_mode,status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'watching')
            """,
            (
                tmdb_id, movie["title"], int(movie["year"]) if str(movie.get("year") or "").isdigit() else None,
                principal.user_id, principal.display_name, now.isoformat(), now.isoformat(), lifecycle["state"],
                lifecycle["region"], lifecycle["theatrical_date"], lifecycle["digital_date"], lifecycle["physical_date"],
                due, payload.maximum_size_gb, payload.minimum_seeders, payload.quality_mode,
            ),
        )
        main.record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="movie_watch_created",
            request_id=None,
            details={"tmdb_id": tmdb_id, "lifecycle_state": lifecycle["state"], "next_check_at": due},
        )
        db.commit()
        row = _watch_row(db, tmdb_id, principal.user_id)
    logger.info("watcher created tmdb_id=%s user_id=%s next_check_at=%s", tmdb_id, principal.user_id, due)
    return _watch_public(row) or {}


async def release_search(
    tmdb_id: int,
    rules: main.ReleaseRules,
    principal: main.CurrentUser,
    expanded: bool = Query(default=False),
    manual_override: bool = Query(default=False),
) -> dict[str, Any]:
    movie = await movie_details(tmdb_id, principal)
    lifecycle = movie["lifecycle"]
    if not manual_override and lifecycle["state"] in {"announced", "theatrical_upcoming"}:
        logger.info("automatic release search deferred tmdb_id=%s lifecycle=%s", tmdb_id, lifecycle["state"])
        return {
            "radarr_movie_id": 0,
            "rules": rules.model_dump(),
            "releases": [],
            "lifecycle": lifecycle,
            "search_state": "deferred_upcoming",
            "search_message": "No releases found, which is expected because this movie has not reached its normal release window yet.",
            "can_expand_recent_search": False,
            "expanded_recent_search": False,
        }
    if manual_override:
        logger.info("manual override release search initiated tmdb_id=%s", tmdb_id)
    result = await release_activity.movie_releases(tmdb_id, rules, principal, expanded=expanded)
    releases = list(result.get("releases") or [])
    eligible = [item for item in releases if item.get("eligible")]
    if not releases:
        state = "no_indexer_results"
        message = "No matching releases were found from your configured sources."
        logger.info("indexer returned zero results tmdb_id=%s", tmdb_id)
    elif not eligible:
        state = "all_rejected"
        reasons: dict[str, int] = {}
        for item in releases:
            for reason in item.get("policy_rejections") or []:
                reasons[str(reason)] = reasons.get(str(reason), 0) + 1
        result["rejection_summary"] = reasons
        message = "Releases were found, but none matched your configured size, quality or seeder requirements."
        logger.info("release results returned but rejected tmdb_id=%s reasons=%s", tmdb_id, json.dumps(reasons, sort_keys=True))
    else:
        state = "results"
        message = f"{len(eligible)} qualifying release{'s' if len(eligible) != 1 else ''} found."
    result["lifecycle"] = lifecycle
    result["search_state"] = state
    result["search_message"] = message
    return result


async def _run_watch_cycle() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await process_due_watches()
        except Exception:
            logger.exception("release watch cycle failed")


async def process_due_watches() -> None:
    now = datetime.now(UTC)
    initialise_watch_database()
    with main.connect_db() as db:
        rows = [dict(row) for row in db.execute(
            """
            SELECT * FROM movie_watches
            WHERE status = 'watching' AND next_check_at <= ?
            ORDER BY tmdb_id, id
            """,
            (now.isoformat(),),
        ).fetchall()]
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["tmdb_id"]), []).append(row)
    for tmdb_id, watches in grouped.items():
        tmdb, _, _ = main.configured_clients(main.load_options())
        try:
            movie = await tmdb.details(tmdb_id)
        except Exception:
            logger.exception("watch metadata refresh failed tmdb_id=%s", tmdb_id)
            continue
        lifecycle = classify_movie(movie)
        due = next_check(lifecycle, now=now)
        should_search = lifecycle["state"] not in {"announced", "theatrical_upcoming"}
        found = False
        if should_search:
            representative = watches[0]
            rules = main.ReleaseRules(
                maximum_size_gb=float(representative["maximum_size_gb"]),
                minimum_seeders=int(representative["minimum_seeders"]),
                quality_mode=str(representative["quality_mode"]),
            )
            try:
                _, releases, _ = await runtime.search_movie_releases(
                    tmdb_id,
                    rules,
                    str(representative["requested_by_id"]),
                    movie=movie,
                )
                found = any(item.get("eligible") for item in releases)
                logger.info("automatic release search initiated tmdb_id=%s qualifying=%s", tmdb_id, found)
            except Exception:
                logger.exception("automatic release search failed tmdb_id=%s", tmdb_id)
        else:
            logger.info("automatic release search deferred tmdb_id=%s lifecycle=%s", tmdb_id, lifecycle["state"])

        with main.connect_db() as db:
            for watch in watches:
                db.execute(
                    """
                    UPDATE movie_watches
                    SET lifecycle_state=?, theatrical_date=?, digital_date=?, physical_date=?,
                        last_checked_at=?, next_check_at=?, qualifying_release_found=?,
                        status=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        lifecycle["state"], lifecycle["theatrical_date"], lifecycle["digital_date"], lifecycle["physical_date"],
                        now.isoformat(), due.isoformat(), 1 if found else 0, "release_found" if found else "watching",
                        now.isoformat(), watch["id"],
                    ),
                )
                if found:
                    main.record_audit(
                        db,
                        actor_id="system",
                        actor_name="MediaHub",
                        action="movie_watch_release_found",
                        request_id=None,
                        details={"tmdb_id": tmdb_id, "watch_id": watch["id"]},
                    )
            db.commit()


@app.on_event("startup")
async def release_lifecycle_startup() -> None:
    initialise_watch_database()
    asyncio.create_task(_run_watch_cycle())


runtime.enhanced_main._replace_route("/api/catalog/movies/{tmdb_id}", "GET", movie_details)
runtime.enhanced_main._replace_route("/api/movies/{tmdb_id}/releases", "POST", release_search)
app.add_api_route("/api/movies/{tmdb_id}/watch", watch_movie, methods=["POST"])


_RELEASE_LIFECYCLE_UI = r"""
<style>
  .lifecycle-card{margin:14px 0 4px;padding:14px 16px;border:1px solid var(--border);border-radius:14px;background:rgba(12,16,24,.8);max-width:680px}
  .lifecycle-label{display:inline-block;font-size:.7rem;font-weight:900;letter-spacing:.09em;padding:5px 8px;border-radius:99px;background:rgba(255,198,90,.12);color:var(--warning)}
  .lifecycle-headline{font-weight:850;margin-top:9px}.lifecycle-copy{color:var(--muted);font-size:.82rem;line-height:1.5;margin-top:6px}.release-date-line{color:#c8d0dd;font-size:.8rem;margin-top:6px}
  @media(max-width:760px){.lifecycle-card{margin-top:12px}.actions .button,.actions a.button{flex:1 1 100%;text-align:center}}
</style>
<script>
  function lifecyclePrimary(movie){
    const state=movie.lifecycle?.state||'released_unknown';
    return ['announced','theatrical_upcoming'].includes(state)?'watch':'request';
  }

  renderDetail=function(){
    const movie=state.movie;
    const genres=(movie.genres||[]).map(item=>item.name).join(' · ');
    const backdrop=movie.backdrop_url?`background-image:url('${esc(movie.backdrop_url)}')`:'';
    const lifecycle=movie.lifecycle||{};
    const message=movie.lifecycle_message||{};
    const watch=movie.watch;
    const primary=lifecyclePrimary(movie);
    const statusCard=`<div class="lifecycle-card"><span class="lifecycle-label">${esc(message.label||'RELEASE STATUS')}</span><div class="lifecycle-headline">${esc(message.headline||'Release availability uncertain')}</div><div class="release-date-line">${esc(movie.digital_release_label||'Digital release date not announced')}</div><div class="lifecycle-copy">${esc(message.explanation||'')}</div>${watch?`<div class="release-date-line">Watching for release · next check ${esc(new Date(watch.next_check_at).toLocaleString())}</div>`:''}</div>`;
    const primaryButton=primary==='watch'?`<button class="button primary" id="watch-release">${watch?'Watching for release':'Watch for release'}</button>`:`<button class="button primary" id="auto-request">Request best release</button>`;
    const secondary=primary==='watch'?`<button class="button" id="search-anyway">Search anyway</button>`:`<button class="button" id="choose-release">Choose a release</button>`;
    document.getElementById('detail').innerHTML=`<div class="detail-hero" style="${backdrop}"><div class="detail-copy"><div class="eyebrow">${esc(genres||'Movie')}</div><h2 id="detail-title">${esc(movie.title)}</h2><div class="muted">${esc(movie.year||'')} · ${movie.runtime_minutes?`${movie.runtime_minutes} min · `:''}★ ${movie.rating.toFixed(1)}</div>${statusCard}<div class="actions">${primaryButton}${secondary}${movie.trailer_url?`<a class="button" href="${esc(movie.trailer_url)}" target="_blank" rel="noopener">Watch trailer</a>`:''}</div></div></div><div class="detail-body"><p class="muted">${esc(movie.overview||'No synopsis is available.')}</p><div id="release-area"></div></div>`;
    const auto=document.getElementById('auto-request');if(auto)auto.addEventListener('click',event=>submitRequest(null,event.currentTarget));
    const choose=document.getElementById('choose-release');if(choose)choose.addEventListener('click',()=>findReleases(false));
    const anyway=document.getElementById('search-anyway');if(anyway)anyway.addEventListener('click',()=>findReleases(true));
    const watchButton=document.getElementById('watch-release');if(watchButton)watchButton.addEventListener('click',()=>watchForRelease(watchButton));
  };

  async function watchForRelease(button){
    button.disabled=true;
    try{
      const watch=await api(`movies/${state.movie.tmdb_id}/watch`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(rules())});
      state.movie.watch=watch;renderDetail();toast('MediaHub is watching for this release.');
    }catch(error){toast(error.message);button.disabled=false;}
  }

  findReleases=async function(manualOverride=false){
    const area=document.getElementById('release-area');
    const selectedRules=rules();
    area.innerHTML=`${rulesHtml(selectedRules)}<div class="empty">Searching available releases...</div>`;
    try{
      const suffix=manualOverride?'?manual_override=true':'';
      const data=await api(`movies/${state.movie.tmdb_id}/releases${suffix}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selectedRules)});
      if(data.search_state==='deferred_upcoming'){
        area.innerHTML=`<div class="empty">${esc(data.search_message)}</div>`;return;
      }
      const rejectionDetails=data.search_state==='all_rejected'&&data.rejection_summary?`<div class="hint" style="margin:10px 0">${Object.entries(data.rejection_summary).map(([reason,count])=>`${count} × ${esc(reason)}`).join(' · ')}</div>`:'';
      area.innerHTML=`${rulesHtml(selectedRules)}<div class="heading"><div><h2>Available releases</h2><p>${esc(data.search_message||`${data.releases.length} results from your configured sources.`)}</p>${rejectionDetails}</div><button class="button" id="rerun-search">Search again</button></div><div class="releases">${data.releases.map(release=>`<article class="release"><div><h4>${esc(release.title)}</h4><div class="release-meta"><span>${esc(release.indexer)}</span><span>${esc(release.quality)}</span><span>${release.size_gb.toFixed(2)} GB</span><span>${release.seeders??'?'} seeders</span></div>${release.policy_rejections.length?`<div class="release-reasons">${esc(release.policy_rejections.join(' · '))}</div>`:''}</div><button class="button ${release.eligible?'primary':''}" data-token="${esc(release.release_token)}" ${release.eligible?'':'disabled'}>${release.eligible?'Download':'Rejected'}</button></article>`).join('')||`<div class="empty">${esc(data.search_message||'No releases were returned.')}</div>`}</div>`;
      document.getElementById('rerun-search').addEventListener('click',()=>findReleases(manualOverride));
      area.querySelectorAll('[data-token]').forEach(button=>button.addEventListener('click',()=>submitRequest(button.dataset.token,button)));
    }catch(error){area.innerHTML=`${rulesHtml(selectedRules)}<div class="empty">${esc(error.message)}</div>`;}
  };
</script>
"""

if "lifecycle-card" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _RELEASE_LIFECYCLE_UI + "\n</body>")
