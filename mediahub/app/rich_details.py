from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query

from . import main, release_lifecycle, runtime

app = release_lifecycle.app
app.version = "0.8.0-dev"


def _rating_cards(movie: dict[str, Any]) -> list[dict[str, Any]]:
    ratings: list[dict[str, Any]] = []
    tmdb_rating = float(movie.get("rating") or 0)
    if tmdb_rating > 0:
        ratings.append(
            {
                "source": "TMDb",
                "value": f"{tmdb_rating:.1f} / 10",
                "url": f"https://www.themoviedb.org/movie/{movie['tmdb_id']}",
            }
        )
    imdb_id = str(movie.get("imdb_id") or "").strip()
    if imdb_id:
        ratings.append(
            {
                "source": "IMDb",
                "value": None,
                "url": f"https://www.imdb.com/title/{imdb_id}/",
                "external_only": True,
            }
        )
    return ratings


def _download_context(tmdb_id: int, principal: main.Principal) -> dict[str, Any] | None:
    with main.connect_db() as db:
        if principal.role in {"admin", "manager"}:
            row = db.execute(
                """
                SELECT id, title, requested_by_name, created_at, updated_at, status,
                       progress, status_message, selected_release_title, estimated_size_gb
                FROM requests
                WHERE media_type='movie' AND external_id=?
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (str(tmdb_id),),
            ).fetchone()
        else:
            row = db.execute(
                """
                SELECT id, title, requested_by_name, created_at, updated_at, status,
                       progress, status_message, selected_release_title, estimated_size_gb
                FROM requests
                WHERE media_type='movie' AND external_id=? AND requested_by_id=?
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (str(tmdb_id), principal.user_id),
            ).fetchone()
    if not row:
        return None
    return {
        "request_id": int(row["id"]),
        "requested_by": str(row["requested_by_name"]),
        "requested_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "status": str(row["status"]),
        "progress": float(row["progress"] or 0),
        "status_message": str(row["status_message"] or ""),
        "selected_release_title": str(row["selected_release_title"] or ""),
        "estimated_size_gb": float(row["estimated_size_gb"] or 0),
        "library_status": "available" if str(row["status"]) == "available" else "not_available",
    }


async def rich_movie_details(
    tmdb_id: int,
    principal: main.CurrentUser,
    context: str = Query(default="browse", pattern="^(browse|downloads)$"),
) -> dict[str, Any]:
    movie = await release_lifecycle.movie_details(tmdb_id, principal)
    movie["ratings"] = _rating_cards(movie)
    movie["context"] = context
    movie["library"] = _download_context(tmdb_id, principal) if context == "downloads" else None
    return movie


async def actor_movies(
    person_id: int,
    principal: main.CurrentUser,
    page: int = Query(default=1, ge=1, le=500),
) -> dict[str, Any]:
    tmdb, _, _ = main.configured_clients(main.load_options())
    try:
        return await tmdb.actor_movies(person_id, page=page)
    except runtime.media_services.MediaServiceError as error:
        raise main.service_http_error(error) from error


async def download_movie_details(
    request_id: int,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    with main.connect_db() as db:
        row = db.execute(
            "SELECT * FROM requests WHERE id=? AND media_type='movie'",
            (request_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Movie download not found")
    item = dict(row)
    if principal.role not in {"admin", "manager"} and item["requested_by_id"] != principal.user_id:
        raise HTTPException(status_code=403, detail="This movie is not available to this user")
    try:
        tmdb_id = int(item["external_id"])
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail="Movie metadata is unavailable") from error
    movie = await release_lifecycle.movie_details(tmdb_id, principal)
    movie["ratings"] = _rating_cards(movie)
    movie["context"] = "downloads"
    movie["library"] = _download_context(tmdb_id, principal)
    return movie


runtime.enhanced_main._replace_route("/api/catalog/movies/{tmdb_id}", "GET", rich_movie_details)
app.add_api_route("/api/catalog/people/{person_id}/movies", actor_movies, methods=["GET"])
app.add_api_route("/api/downloads/{request_id}/details", download_movie_details, methods=["GET"])


_RICH_DETAILS_UI = r"""
<style>
  .detail-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:18px}.section-title{font-size:.82rem;text-transform:uppercase;letter-spacing:.1em;color:#aeb8c8;font-weight:900;margin:18px 0 10px}.ratings-grid{display:flex;flex-wrap:wrap;gap:10px}.rating-card{min-width:120px;padding:11px 13px;border:1px solid var(--border);border-radius:13px;background:#0c1018;text-decoration:none;color:var(--text)}.rating-card strong{display:block;font-size:.75rem;color:var(--muted);margin-bottom:4px}.cast-strip{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px}.cast-card{border:1px solid var(--border);border-radius:13px;background:#0c1018;color:var(--text);padding:10px;text-align:left;min-height:70px}.cast-card img{width:42px;height:42px;object-fit:cover;border-radius:50%;float:left;margin-right:9px}.cast-name{font-weight:850}.cast-role{font-size:.75rem;color:var(--muted);margin-top:3px}.library-card{padding:14px;border:1px solid var(--border);border-radius:14px;background:#0c1018;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.library-card div span{display:block;color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;margin-bottom:3px}.modal .dialog{scroll-behavior:smooth}.close:focus,.button:focus,.cast-card:focus,.rating-card:focus{outline:2px solid var(--accent-2);outline-offset:2px}@media(max-width:760px){.cast-strip{grid-template-columns:1fr 1fr}.rating-card{flex:1 1 42%}}
</style>
<script>
  let detailContext='browse';
  const baseOpenMovie=typeof openMovie==='function'?openMovie:null;
  if(baseOpenMovie){
    openMovie=async function(id){detailContext='browse';return await baseOpenMovie(id);};
  }

  function richRatings(movie){
    const cards=(movie.ratings||[]).map(r=>`<a class="rating-card" href="${esc(r.url||'#')}" target="_blank" rel="noopener noreferrer" aria-label="Open ${esc(r.source)} rating"><strong>${esc(r.source)}</strong>${esc(r.value||'View rating')}</a>`).join('');
    return cards?`<div class="section-title">Ratings & reviews</div><div class="ratings-grid">${cards}</div>`:'';
  }
  function richCast(movie){
    const cards=(movie.cast||[]).map(actor=>`<button class="cast-card" data-person-id="${actor.id||''}" data-person-name="${esc(actor.name||'')}" aria-label="View movies starring ${esc(actor.name||'actor')}">${actor.profile_url?`<img src="${esc(actor.profile_url)}" alt="${esc(actor.name||'Actor')}">`:''}<div class="cast-name">${esc(actor.name||'')}</div><div class="cast-role">${esc(actor.character||'')}</div></button>`).join('');
    return cards?`<div class="section-title">Cast</div><div class="cast-strip">${cards}</div>`:'';
  }
  function libraryInfo(movie){
    const lib=movie.library;if(!lib)return '';
    return `<div class="section-title">Download & library</div><div class="library-card"><div><span>Status</span>${esc(lib.status||'')}</div><div><span>Requested by</span>${esc(lib.requested_by||'')}</div><div><span>Requested</span>${esc(new Date(lib.requested_at).toLocaleString())}</div><div><span>Progress</span>${Number(lib.progress||0).toFixed(0)}%</div><div><span>Release</span>${esc(lib.selected_release_title||'Not recorded')}</div><div><span>Size</span>${Number(lib.estimated_size_gb||0).toFixed(2)} GB</div></div>`;
  }
  function bindRichDetail(){
    document.querySelectorAll('[data-person-id]').forEach(button=>button.addEventListener('click',()=>showActorMovies(button.dataset.personId,button.dataset.personName)));
  }
  async function showActorMovies(personId,name){
    if(!personId){document.getElementById('search').value=name;closeModal();loadMovies(true);return;}
    try{
      const data=await api(`catalog/people/${personId}/movies`);
      closeModal();
      state.query='';state.collection='popular';state.movies=data.movies||[];state.page=Number(data.page||1);state.totalPages=Number(data.total_pages||1);
      document.getElementById('search').value='';
      document.getElementById('movie-heading').textContent=`Movies with ${name}`;
      renderMovies();
    }catch(error){toast(error.message);}
  }
  renderDetail=function(){
    const movie=state.movie;const genres=(movie.genres||[]).map(item=>item.name).join(' · ');const backdrop=movie.backdrop_url?`background-image:url('${esc(movie.backdrop_url)}')`:'';const lifecycle=movie.lifecycle||{};const message=movie.lifecycle_message||{};const watch=movie.watch;const primary=lifecyclePrimary(movie);const downloads=movie.context==='downloads';
    const statusCard=`<div class="lifecycle-card"><span class="lifecycle-label">${esc(message.label||'RELEASE STATUS')}</span><div class="lifecycle-headline">${esc(message.headline||'Release availability uncertain')}</div><div class="release-date-line">${esc(movie.digital_release_label||'Digital release date not announced')}</div><div class="lifecycle-copy">${esc(message.explanation||'')}</div>${watch&&!downloads?`<div class="release-date-line">Watching for release · next check ${esc(new Date(watch.next_check_at).toLocaleString())}</div>`:''}</div>`;
    let actionButtons='';
    if(!downloads){const primaryButton=primary==='watch'?`<button class="button primary" id="watch-release">${watch?'Watching for release':'Watch for release'}</button>`:`<button class="button primary" id="auto-request">Request best release</button>`;const secondary=primary==='watch'?`<button class="button" id="search-anyway">Search anyway</button>`:`<button class="button" id="choose-release">Choose a release</button>`;actionButtons=primaryButton+secondary;}
    if(movie.trailer_url)actionButtons+=`<a class="button" href="${esc(movie.trailer_url)}" target="_blank" rel="noopener noreferrer">Watch trailer</a>`;
    document.getElementById('detail').innerHTML=`<div class="detail-hero" style="${backdrop}"><div class="detail-copy"><div class="eyebrow">${esc(genres||'Movie')}</div><h2 id="detail-title">${esc(movie.title)}</h2><div class="muted">${esc(movie.year||'')} ${movie.runtime_minutes?`· ${movie.runtime_minutes} min`:''}${movie.certification?` · ${esc(movie.certification)}`:''}</div>${statusCard}<div class="actions">${actionButtons}</div></div></div><div class="detail-body"><div class="detail-grid"><p class="muted">${esc(movie.overview||'No synopsis is available.')}</p>${movie.director?`<div><span class="muted">Directed by</span> <strong>${esc(movie.director.name||movie.director)}</strong></div>`:''}${richRatings(movie)}${richCast(movie)}${libraryInfo(movie)}<div id="release-area"></div></div></div>`;
    if(!downloads){const auto=document.getElementById('auto-request');if(auto)auto.addEventListener('click',event=>submitRequest(null,event.currentTarget));const choose=document.getElementById('choose-release');if(choose)choose.addEventListener('click',()=>findReleases(false));const anyway=document.getElementById('search-anyway');if(anyway)anyway.addEventListener('click',()=>findReleases(true));const watchButton=document.getElementById('watch-release');if(watchButton)watchButton.addEventListener('click',()=>watchForRelease(watchButton));}
    bindRichDetail();
  };

  const baseRenderDownloads=typeof renderDownloads==='function'?renderDownloads:null;
  if(baseRenderDownloads){
    renderDownloads=function(items){baseRenderDownloads(items);document.querySelectorAll('.download').forEach((card,index)=>{const item=items[index];if(!item)return;card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-label',`View details for ${item.title}`);const open=async()=>{try{detailContext='downloads';state.movie=await api(`downloads/${item.id}/details`);renderDetail();document.getElementById('modal').classList.remove('hidden');document.getElementById('close').focus();}catch(error){toast(error.message);}};card.addEventListener('click',open);card.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open();}});});};
  }
</script>
"""

if "ratings-grid" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _RICH_DETAILS_UI + "\n</body>")
