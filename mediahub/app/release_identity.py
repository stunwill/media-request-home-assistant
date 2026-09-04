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


@dataclass(frozen=True)
class IdentityResult:
    state: Literal["strong", "acceptable", "suspicious", "rejected"]
    score: int
    reasons: tuple[str, ...]
    matched_title: str | None = None
    release_year: int | None = None

    @property
    def eligible(self) -> bool:
        return self.state in {"strong", "acceptable"}


def normalise_title(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"[._'’`\-]+", " ", text)
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


def validate_movie_release(movie: dict[str, Any], release: dict[str, Any]) -> IdentityResult:
    raw = str(release.get("title") or "")
    if not raw:
        return IdentityResult("rejected", 0, ("Release title is unavailable",))
    lowered = normalise_title(raw)
    if any(pattern.search(lowered) for pattern in _TV_EPISODE_PATTERNS):
        return IdentityResult("rejected", 0, ("Appears to be a TV episode",))
    if any(pattern.search(lowered) for pattern in _TV_SEASON_PATTERNS):
        return IdentityResult("rejected", 5, ("Appears to be a TV season release",))

    candidates = _movie_titles(movie)
    best_title: str | None = None
    best_score = 0
    for candidate in candidates:
        matched, score = _title_prefix_match(raw, candidate)
        if matched and score > best_score:
            best_title, best_score = candidate, score
    if best_title is None:
        return IdentityResult("rejected", best_score, ("Does not match requested movie title",))

    requested_year = int(movie.get("year") or 0) if str(movie.get("year") or "").isdigit() else None
    release_year = _release_year(raw)
    reasons = ["Strong title match"]
    score = best_score
    if requested_year and release_year:
        delta = abs(requested_year - release_year)
        if delta == 0:
            score += 20
            reasons.append("Release year matches")
        elif delta == 1:
            score += 10
            reasons.append("Year within accepted range")
        elif delta >= 2:
            return IdentityResult("rejected", max(0, score - 35), ("Conflicting release year",), best_title, release_year)
    state: Literal["strong", "acceptable", "suspicious", "rejected"] = "strong" if score >= 105 else "acceptable"
    return IdentityResult(state, score, tuple(reasons), best_title, release_year)


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
    rejections = [str(value) for value in result.get("policy_rejections") or []]
    if not identity.eligible:
        rejections.extend(identity.reasons)
    result["match_state"] = identity.state
    result["match_score"] = identity.score
    result["match_reasons"] = list(identity.reasons)
    result["policy_rejections"] = list(dict.fromkeys(rejections))
    result["eligible"] = identity.eligible and not result["policy_rejections"]
    return result
