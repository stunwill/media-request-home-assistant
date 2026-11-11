from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal


_TV_EPISODE_PATTERNS = (
    re.compile(r"\bs\d{1,2}e\d{1,3}\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}x\d{1,3}\b", re.IGNORECASE),
)
_TV_SEASON_PATTERNS = (
    re.compile(r"\bs\d{1,2}\b", re.IGNORECASE),
    re.compile(r"\bseason[ ._-]*\d{1,2}\b", re.IGNORECASE),
)
_YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")
_RELEASE_MARKERS = {
    "1080p", "720p", "2160p", "bluray", "blu", "ray", "web", "webdl", "webrip",
    "hdtv", "x264", "x265", "h264", "h265", "hevc", "aac", "dd", "ddp", "dts",
    "atmos", "hdr", "dv", "remux", "proper", "repack", "extended", "directors", "cut",
}

REJECTION_PRECEDENCE = {
    "identity": 0,
    "library_upgrade": 1,
    "arr": 2,
    "mediahub_policy": 3,
    "indexer_availability": 4,
    "other": 5,
}
REJECTION_LABELS = {
    "identity": "DOESN'T MATCH MEDIA",
    "library_upgrade": "BLOCKED BY LIBRARY / UPGRADE STATE",
    "arr": "BLOCKED BY MEDIA MANAGER",
    "mediahub_policy": "BLOCKED BY MEDIAHUB PRESET",
    "indexer_availability": "RELEASE UNAVAILABLE",
    "other": "UNAVAILABLE",
}


@dataclass(frozen=True)
class IdentityResult:
    state: Literal["strong", "acceptable", "suspicious", "rejected"]
    score: int
    reasons: tuple[str, ...]
    matched_title: str | None = None
    release_year: int | None = None
    selected_year: int | None = None
    year_tolerated: bool = False

    @property
    def status(self) -> str:
        return "accepted" if self.eligible else "uncertain" if self.state == "suspicious" else "rejected"

    @property
    def eligible(self) -> bool:
        return self.state in {"strong", "acceptable"}


def seeder_count(value):
    """Unknown, negative, fractional or malformed counts never mean confirmed zero."""
    if isinstance(value,bool):
        return None
    text=str(value).strip() if value is not None else ''
    return int(text) if text.isascii() and text.isdigit() and len(text)<=10 else None


def normalise_title(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"['’`]", "", text)
    text = re.sub(r"[._\-]+", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value: str) -> list[str]:
    return [token for token in normalise_title(value).split() if token and token not in _RELEASE_MARKERS]


def _release_year(title: str) -> int | None:
    match = _YEAR_PATTERN.search(title)
    return int(match.group(1)) if match else None


def _movie_titles(movie: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("title", "original_title"):
        value = str(movie.get(key) or "").strip()
        if value:
            values.append(value)
    for item in movie.get("alternative_titles") or []:
        value = str(item.get("title") if isinstance(item, dict) else item or "").strip()
        if value:
            values.append(value)
    # Grammatical alternate title, not arbitrary first-word/fuzzy truncation.
    # Example: Birdman or (The Unexpected Virtue of Ignorance).
    for title in list(values):
        match = re.fullmatch(r'(.+?)\s+or\s+\(.+\)', title, flags=re.I)
        if match and match[1].strip():
            values.append(match[1].strip())
    return list(dict.fromkeys(values))


def _title_prefix_match(release_title: str, candidate_title: str) -> tuple[bool, int]:
    release_tokens = _tokens(release_title)
    title_tokens = _tokens(candidate_title)
    if not title_tokens or len(release_tokens) < len(title_tokens):
        return False, 0
    if release_tokens[: len(title_tokens)] == title_tokens:
        return True, 100
    release_set, title_set = set(release_tokens), set(title_tokens)
    overlap = len(release_set & title_set) / max(1, len(title_set))
    return False, int(overlap * 60)


def _safe_diagnostic(value: Any) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return None
    lowered = text.casefold()
    sensitive_markers = (
        "api key", "apikey", "api_key", "token", "password", "credential", "magnet:",
        "downloadurl", "download url", "guid", "passkey", "cookie", "authorization", "secret", "http://", "https://",
    )
    return None if any(marker in lowered for marker in sensitive_markers) else text[:500]


def rejection_detail(
    category: str,
    message: str,
    *,
    code: str,
    service: str | None = None,
    raw_message: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "category": category if category in REJECTION_PRECEDENCE else "other",
        "code": code,
        "message": str(message),
    }
    if service:
        detail["service"] = service
    safe_raw = _safe_diagnostic(raw_message)
    if safe_raw and safe_raw != message:
        detail["raw_message"] = safe_raw
    return detail


def classify_arr_rejection(reason: Any, *, service: str) -> dict[str, Any]:
    raw = " ".join(str(reason or "").split()).strip() or f"{service} rejected this release"
    lowered = raw.casefold()
    library_markers = (
        "meets cutoff", "cutoff", "quality profile does not allow upgrades", "does not allow upgrades",
        "existing file", "release in queue", "already queued", "already exists", "upgrade",
    )
    unavailable_markers = (
        "not enough seeders", "fewer than", "indexer", "unavailable", "not available",
        "unable to parse", "unknown movie", "unknown series",
    )
    if any(marker in lowered for marker in library_markers):
        message = "Existing or queued library quality currently prevents this upgrade."
        return rejection_detail(
            "library_upgrade",
            message,
            code="library_cutoff_or_upgrade",
            service=service,
            raw_message=raw,
        )
    if any(marker in lowered for marker in unavailable_markers):
        return rejection_detail(
            "indexer_availability",
            raw,
            code="release_unavailable",
            service=service,
            raw_message=raw,
        )
    return rejection_detail(
        "arr",
        raw,
        code="media_manager_rejection",
        service=service,
        raw_message=raw,
    )


def primary_rejection(details: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not details:
        return None
    return min(
        details,
        key=lambda item: REJECTION_PRECEDENCE.get(str(item.get("category") or "other"), 99),
    )


def with_rejection_details(
    result: dict[str, Any],
    details: list[dict[str, Any]],
) -> dict[str, Any]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for detail in details:
        key = (
            str(detail.get("category") or "other"),
            str(detail.get("code") or ""),
            str(detail.get("message") or ""),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(detail)
    result["rejection_details"] = deduped
    result["policy_rejections"] = [str(item["message"]) for item in deduped]
    primary = primary_rejection(deduped)
    result["primary_rejection"] = primary
    result["rejection_label"] = (
        REJECTION_LABELS.get(str(primary.get("category")), "UNAVAILABLE") if primary else None
    )
    return result


def movie_year_evidence(movie: dict[str, Any]) -> dict[int, str]:
    """Use selected-movie metadata only, never years asserted by a torrent."""
    years = {}
    for key in ("production_year", "premiere_date", "theatrical_release_date",
                "digital_release_date", "release_date"):
        value = str(movie.get(key) or "")[:4]
        if value.isdigit() and 1800 <= int(value) <= 2199:
            years[int(value)] = key.replace("_", " ")
    dates = movie.get("release_dates") or {}
    if isinstance(dates, dict):
        labels = {1: "premiere", 2: "limited theatrical", 3: "theatrical", 4: "digital", 5: "physical", 6: "TV"}
        for region, records in dates.items():
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                value = str(record.get("release_date") or "")[:4]
                if value.isdigit() and 1800 <= int(value) <= 2199:
                    years[int(value)] = f"TMDb {region} {labels.get(record.get('type'), 'release')} date"
    return years


def _identifier(value: Any) -> str:
    text = str(value or "").strip().lower().removeprefix("tt")
    return text.lstrip("0") if text.isascii() and text.isdigit() else ""


def validate_movie_release(movie: dict[str, Any], release: dict[str, Any]) -> IdentityResult:
    raw = str(release.get("title") or "")
    year_text = str(movie.get("year") or str(movie.get("release_date") or "")[:4])
    requested_year = int(year_text) if year_text.isdigit() else None
    authoritative_match = False
    identifier_conflict = False
    # Inspect every supplied ID, including tagged IDs in filenames. A matching ID
    # must never hide a conflicting ID from the other namespace or another field.
    for movie_key, release_keys in (("imdb_id", ("imdbId", "imdb_id")), ("tmdb_id", ("tmdbId", "tmdb_id"))):
        expected = _identifier(movie.get(movie_key))
        values = [release.get(key) for key in release_keys]
        pattern = r"\btt\d+\b" if movie_key == "imdb_id" else r"\btmdb[ ._:=\-]+(\d+)\b"
        values.extend(re.findall(pattern, raw, re.I))
        returned = {_identifier(value) for value in values} - {""}
        if expected and returned - {expected}:
            identifier_conflict = True
        authoritative_match |= bool(expected and expected in returned)
    lowered = normalise_title(raw)
    if any(pattern.search(lowered) for pattern in _TV_EPISODE_PATTERNS + _TV_SEASON_PATTERNS):
        return IdentityResult("rejected", 0, ("Appears to be a TV episode or season release",), selected_year=requested_year)
    if not raw and not authoritative_match:
        return IdentityResult("rejected", 0, ("Release title is unavailable",), selected_year=requested_year)

    best_title = None
    tail = lowered
    for candidate in _movie_titles(movie):
        normal = normalise_title(candidate)
        if not normal or not (lowered == normal or lowered.startswith(normal + " ")):
            continue
        remainder = lowered[len(normal):].strip()
        tokens = remainder.split()
        # Exact title boundary, never arbitrary fuzzy overlap or extra title words.
        boundary = not tokens or bool(_YEAR_PATTERN.fullmatch(tokens[0])) or tokens[0] in _RELEASE_MARKERS
        if boundary and (best_title is None or len(candidate) > len(best_title)):
            best_title, tail = candidate, remainder
    release_year = _release_year(tail)
    delta = abs(requested_year - release_year) if requested_year and release_year else None
    def result(state, score, reasons):
        return IdentityResult(state, score, tuple(reasons), best_title, release_year,
                              requested_year, bool(delta and state in {"strong", "acceptable"}))
    if identifier_conflict:
        return result("rejected", 0, ["Conflicting authoritative movie identifier"])
    if authoritative_match:
        return result("strong", 140, ["Verified matching movie identifier"] +
                      ([f"Alternate release year ({release_year} vs {requested_year}) verified by movie identifier"] if delta else []))
    if best_title is None:
        return result("rejected", 0, ["Does not match requested movie title"])
    reasons = ["Strong title match"]
    if normalise_title(best_title) != normalise_title(movie.get("title")):
        reasons.append("Known original or alternative title")
    evidence = movie_year_evidence(movie)
    if delta == 0:
        return result("strong", 120, reasons + ["Release year matches"])
    if delta and release_year in evidence:
        return result("strong", 120, reasons + [f"Alternate release year ({release_year} vs {requested_year}) verified by {evidence[release_year]}"])
    if delta == 1:
        return result("acceptable", 100, reasons + [f"Alternate release year ({release_year} vs {requested_year})", "One-year difference tolerated"])
    if delta == 2:
        return result("suspicious", 65, reasons + ["Year differs by 2", "Additional verification required"])
    if delta:
        return result("rejected", 30, ["Conflicting release year"])
    grammatical_alias = best_title not in [movie.get("title"), movie.get("original_title")] and any(
        re.fullmatch(re.escape(best_title) + r"\s+or\s+\(.+\)", str(movie.get(key) or ""), re.I)
        for key in ("title", "original_title"))
    if grammatical_alias and not release_year:
        return result("suspicious", 60, reasons + ["Shortened title needs a compatible year or movie identifier"])
    return result("acceptable", 95, reasons + ["Year unavailable; title matched without year verification"])


def validate_tv_release(
    *,
    series_title: str,
    release: dict[str, Any],
    season_number: int,
    episode_number: int | None,
    structured_full_season: bool | None = None,
) -> IdentityResult:
    raw = str(release.get("title") or "")
    matched, score = _title_prefix_match(raw, series_title)
    if not matched:
        return IdentityResult("rejected", score, ("Does not match requested TV series",))
    normal = normalise_title(raw)
    season_pattern = re.compile(rf"\bs0*{season_number}\b", re.IGNORECASE)
    if episode_number is not None:
        episode_patterns = (
            re.compile(rf"\bs0*{season_number}e0*{episode_number}\b", re.IGNORECASE),
            re.compile(rf"\b0*{season_number}x0*{episode_number}\b", re.IGNORECASE),
        )
        if not any(pattern.search(normal) for pattern in episode_patterns):
            return IdentityResult("rejected", score, ("Release does not match requested episode",))
        return IdentityResult("strong", score + 25, ("Series and episode match",))
    if structured_full_season is False:
        return IdentityResult("rejected", score, ("Release is not a full season pack",))
    if not season_pattern.search(normal) and structured_full_season is not True:
        return IdentityResult("rejected", score, ("Release does not match requested season",))
    return IdentityResult("strong", score + 20, ("Series and season match",))


def apply_identity(public: dict[str, Any], identity: IdentityResult) -> dict[str, Any]:
    result = dict(public)
    details = [dict(item) for item in result.get("rejection_details") or []]
    if not details:
        details = [
            rejection_detail("other", str(value), code="legacy_rejection")
            for value in result.get("policy_rejections") or []
        ]
    if not identity.eligible:
        details.extend(
            rejection_detail(
                "identity",
                str(reason),
                code="identity_mismatch",
            )
            for reason in identity.reasons
        )
    result["identity_status"] = identity.status
    result["selected_movie_year"] = identity.selected_year
    result["torrent_release_year"] = identity.release_year
    result["year_tolerated"] = identity.year_tolerated
    result["match_state"] = identity.state
    result["match_score"] = identity.score
    result["match_reasons"] = list(identity.reasons)
    with_rejection_details(result, details)
    result["eligible"] = identity.eligible and not result["rejection_details"]
    return result
