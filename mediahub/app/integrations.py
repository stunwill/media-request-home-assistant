from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

import httpx


IntegrationName = Literal["tmdb", "prowlarr", "radarr", "sonarr", "qbittorrent"]


@dataclass(frozen=True)
class IntegrationConfig:
    name: IntegrationName
    url: str = ""
    api_key: str = ""
    username: str = ""
    password: str = ""

    @property
    def configured(self) -> bool:
        if self.name == "tmdb":
            return bool(self.api_key.strip())
        if self.name == "qbittorrent":
            return bool(self.url.strip() and self.username.strip() and self.password)
        return bool(self.url.strip() and self.api_key.strip())


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
                headers={"User-Agent": "MediaHub/0.2"},
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

        login = await client.post(
            f"{base_url}/api/v2/auth/login",
            data={"username": config.username, "password": config.password},
        )
        login.raise_for_status()
        if login.text.strip() != "Ok.":
            raise ValueError("qBittorrent rejected credentials")
        response = await client.get(f"{base_url}/api/v2/app/version")
        response.raise_for_status()
        return {"version": response.text.strip()}

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
            username=str(integrations.get("qbittorrent_username", "")),
            password=str(integrations.get("qbittorrent_password", "")),
        ),
    ]
