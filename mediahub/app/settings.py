from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


APP_DATA = Path("/data")
OPTIONS_FILE = APP_DATA / "options.json"
SETTINGS_FILE = APP_DATA / "mediahub-settings.json"

INTEGRATION_FIELDS = {
    "tmdb_api_key",
    "prowlarr_url",
    "prowlarr_api_key",
    "radarr_url",
    "radarr_api_key",
    "sonarr_url",
    "sonarr_api_key",
    "qbittorrent_url",
    "qbittorrent_username",
    "qbittorrent_password",
}
SECRET_FIELDS = {
    "tmdb_api_key",
    "prowlarr_api_key",
    "radarr_api_key",
    "sonarr_api_key",
    "qbittorrent_password",
}
URL_FIELDS = {
    "prowlarr_url",
    "radarr_url",
    "sonarr_url",
    "qbittorrent_url",
}

DEFAULT_OPTIONS: dict[str, Any] = {
    "storage": {
        "media_path": "/media",
        "minimum_free_gb": 50,
        "safety_margin_gb": 10,
        "reservation_multiplier": 1.5,
    },
    "approvals": {"auto_approve": True},
    "integrations": {},
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def load_options(
    options_file: Path = OPTIONS_FILE,
    settings_file: Path = SETTINGS_FILE,
) -> dict[str, Any]:
    options = _merge(DEFAULT_OPTIONS, _read_json(options_file))
    return _merge(options, _read_json(settings_file))


def normalise_service_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""

    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Service URLs must use http:// or https:// and include a hostname")
    if parts.username or parts.password:
        raise ValueError("Credentials must not be embedded in a service URL")
    if parts.query or parts.fragment:
        raise ValueError("Service URLs must not include a query string or fragment")

    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def save_integration_settings(
    updates: dict[str, str],
    *,
    clear_secrets: Iterable[str] = (),
    settings_file: Path = SETTINGS_FILE,
) -> dict[str, Any]:
    invalid_fields = set(updates) - INTEGRATION_FIELDS
    if invalid_fields:
        raise ValueError(f"Unknown integration fields: {', '.join(sorted(invalid_fields))}")

    invalid_clear_fields = set(clear_secrets) - SECRET_FIELDS
    if invalid_clear_fields:
        raise ValueError(f"Unknown secret fields: {', '.join(sorted(invalid_clear_fields))}")

    settings = _read_json(settings_file)
    integrations = settings.setdefault("integrations", {})
    if not isinstance(integrations, dict):
        integrations = {}
        settings["integrations"] = integrations

    for field, value in updates.items():
        if field in URL_FIELDS:
            integrations[field] = normalise_service_url(value)
        elif field in SECRET_FIELDS and not value:
            continue
        else:
            integrations[field] = value.strip() if field != "qbittorrent_password" else value

    for field in clear_secrets:
        integrations[field] = ""

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=settings_file.parent,
            prefix=f".{settings_file.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            os.chmod(temporary_path, 0o600)
            json.dump(settings, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, settings_file)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    os.chmod(settings_file, 0o600)
    return settings


def _public_url(value: Any) -> str:
    candidate = str(value).strip()
    if not candidate:
        return ""
    parts = urlsplit(candidate)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        return ""
    return candidate


def public_integration_settings(options: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = options.get("integrations", {})
    return {
        "tmdb": {
            "api_key_set": bool(str(values.get("tmdb_api_key", "")).strip()),
        },
        "prowlarr": {
            "url": _public_url(values.get("prowlarr_url", "")),
            "api_key_set": bool(str(values.get("prowlarr_api_key", "")).strip()),
        },
        "radarr": {
            "url": _public_url(values.get("radarr_url", "")),
            "api_key_set": bool(str(values.get("radarr_api_key", "")).strip()),
        },
        "sonarr": {
            "url": _public_url(values.get("sonarr_url", "")),
            "api_key_set": bool(str(values.get("sonarr_api_key", "")).strip()),
        },
        "qbittorrent": {
            "url": _public_url(values.get("qbittorrent_url", "")),
            "username": str(values.get("qbittorrent_username", "")),
            "password_set": bool(values.get("qbittorrent_password", "")),
        },
    }
