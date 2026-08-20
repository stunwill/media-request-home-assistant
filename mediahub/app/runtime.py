from __future__ import annotations

import posixpath
from typing import Any

from . import enhanced_main, main, media_services

app = enhanced_main.app

_original_analyse_download_workflow = media_services.analyse_download_workflow


def analyse_download_workflow(
    radarr: dict[str, Any],
    qbittorrent: dict[str, Any],
) -> dict[str, Any]:
    """Normalise qBittorrent paths before applying the existing safety analysis."""
    qbittorrent_settings = dict(qbittorrent)
    completed = str(qbittorrent_settings.get("completed_path") or "").strip()
    category = str(qbittorrent_settings.get("radarr_category_path") or "").strip()
    if category and completed and not posixpath.isabs(category):
        qbittorrent_settings["radarr_category_path"] = posixpath.join(completed, category)

    result = _original_analyse_download_workflow(radarr, qbittorrent_settings)
    for check in result.get("checks", []):
        if check.get("message") == "Radarr library path could not be determined.":
            check["message"] = (
                "Select a Radarr movie root folder in Setup so MediaHub can validate "
                "the library path."
            )
    return result


async def _radarr_duplicate(radarr: Any, tmdb_id: int) -> dict[str, Any] | None:
    """Reject only movies that Radarr confirms are queued or already have a file."""
    movie = await radarr.ensure_movie(tmdb_id)
    movie_id = int(movie.get("id") or 0)
    if movie.get("hasFile"):
        return {"status": "available", "radarr_movie_id": movie_id}

    queue = await radarr.queue()
    if movie_id and any(int(item.get("movieId") or 0) == movie_id for item in queue):
        return {"status": "queued", "radarr_movie_id": movie_id}
    return None


# Keep the public modules consistent. Existing FastAPI route functions resolve these
# globals at request time, so patching them here avoids duplicating the route layer.
media_services.analyse_download_workflow = analyse_download_workflow
main.analyse_download_workflow = analyse_download_workflow
enhanced_main._radarr_duplicate = _radarr_duplicate
