from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx


IntegrationName = Literal["tmdb", "prowlarr", "radarr", "sonarr", "qbittorrent"]


@dataclass(frozen=True)
class IntegrationConfig:
    name: IntegrationName
    url: str = ""
    api_key: str = ""
    username: str = ""
    password: str = ""
    auth_method: str = "password"

    @property
    def configured(self) -> bool:
        if self.name == "tmdb":
            return bool(self.api_key.strip())
        if self.name == "qbittorrent":
            credentials_set = (
                bool(self.api_key.strip())
                if self.auth_method == "api_key"
                else bool(self.username.strip() and self.password)
            )
            return bool(self.url.strip() and credentials_set)
        return bool(self.url.strip() and self.api_key.strip())


def qbittorrent_headers(base_url: str, api_key: str = "") -> dict[str, str]:
    parts = urlsplit(base_url.rstrip("/"))
    origin = f"{parts.scheme}://{parts.netloc}"
    headers = {
        "User-Agent": "MediaHub/0.6.1",
        "Origin": origin,
        "Referer": f"{base_url.rstrip('/')}/",
    }
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


async def authenticate_qbittorrent(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    username: str = "",
    password: str = "",
    api_key: str = "",
) -> str:
    headers = qbittorrent_headers(base_url, api_key)
    if not api_key.strip():
        login = await client.post(
            f"{base_url.rstrip('/')}/api/v2/auth/login",
            data={"username": username, "password": password},
            headers=headers,
        )
        login.raise_for_status()

    response = await client.get(
        f"{base_url.rstrip('/')}/api/v2/app/version",
        headers=headers,
    )
    response.raise_for_status()
    version = response.text.strip()
    if not version:
        raise ValueError("qBittorrent returned an empty version")
    return version


class IntegrationTester:
    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    async def test(self, config: IntegrationConfig) -> dict[str, Any]:
        if not config.configured:
            return self._result(config.name, "not_configured")

        started = perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "MediaHub/0.6.1"},
                transport=self.transport,
            ) as client:
                details = await self._test_service(client, config)
        except httpx.TimeoutException:
            return self._result(config.name, "unavailable", started, "Connection timed out")
        except httpx.HTTPStatusError as error:
            status = "authentication_failed" if error.response.status_code in {401, 403} else "unavailable"
            return self._result(
                config.name,
                status,
                started,
                f"Service returned HTTP {error.response.status_code}",
            )
        except httpx.RequestError:
            return self._result(config.name, "unavailable", started, "Unable to reach service")
        except (KeyError, TypeError, ValueError):
            return self._result(config.name, "invalid_response", started, "Service returned an unexpected response")

        return self._result(config.name, "connected", started, details=details)

    async def test_all(self, configs: list[IntegrationConfig]) -> list[dict[str, Any]]:
        return list(await asyncio.gather(*(self.test(config) for config in configs)))

    async def _test_service(
        self, client: httpx.AsyncClient, config: IntegrationConfig
    ) -> dict[str, Any]:
        if config.name == "tmdb":
            response = await client.get(
                "https://api.themoviedb.org/3/configuration",
                params={"api_key": config.api_key},
            )
            response.raise_for_status()
            payload = response.json()
            return {"image_base_url": payload["images"]["secure_base_url"]}

        base_url = config.url.rstrip("/")
        if config.name in {"prowlarr", "radarr", "sonarr"}:
            response = await client.get(
                f"{base_url}/api/v3/system/status",
                headers={"X-Api-Key": config.api_key},
            )
            response.raise_for_status()
            payload = response.json()
            return {
                "app_name": str(payload.get("appName", config.name.title())),
                "version": str(payload["version"]),
            }

        version = await authenticate_qbittorrent(
            client,
            base_url=base_url,
            username=config.username,
            password=config.password,
            api_key=config.api_key if config.auth_method == "api_key" else "",
        )
        return {"version": version}

    @staticmethod
    def _result(
        name: IntegrationName,
        status: str,
        started: float | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": name,
            "status": status,
            "configured": status != "not_configured",
        }
        if started is not None:
            result["latency_ms"] = round((perf_counter() - started) * 1000)
        if message:
            result["message"] = message
        if details:
            result["details"] = details
        return result


def integration_configs(options: dict[str, Any]) -> list[IntegrationConfig]:
    integrations = options.get("integrations", {})
    return [
        IntegrationConfig(name="tmdb", api_key=str(integrations.get("tmdb_api_key", ""))),
        IntegrationConfig(
            name="prowlarr",
            url=str(integrations.get("prowlarr_url", "")),
            api_key=str(integrations.get("prowlarr_api_key", "")),
        ),
        IntegrationConfig(
            name="radarr",
            url=str(integrations.get("radarr_url", "")),
            api_key=str(integrations.get("radarr_api_key", "")),
        ),
        IntegrationConfig(
            name="sonarr",
            url=str(integrations.get("sonarr_url", "")),
            api_key=str(integrations.get("sonarr_api_key", "")),
        ),
        IntegrationConfig(
            name="qbittorrent",
            url=str(integrations.get("qbittorrent_url", "")),
            api_key=str(integrations.get("qbittorrent_api_key", "")),
            username=str(integrations.get("qbittorrent_username", "")),
            password=str(integrations.get("qbittorrent_password", "")),
            auth_method=str(integrations.get("qbittorrent_auth_method", "password")),
        ),
    ]
