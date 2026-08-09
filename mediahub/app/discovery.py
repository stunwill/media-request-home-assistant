from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ServiceDefinition:
    name: str
    aliases: tuple[str, ...]
    port: int


SERVICES = (
    ServiceDefinition("prowlarr", ("prowlarr",), 9696),
    ServiceDefinition("radarr", ("radarr",), 7878),
    ServiceDefinition("sonarr", ("sonarr",), 8989),
    ServiceDefinition("qbittorrent", ("qbittorrent", "qbit torrent", "qbit"), 8080),
)


class SupervisorDiscovery:
    def __init__(
        self,
        *,
        base_url: str = "http://supervisor",
        token: str | None = None,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token if token is not None else os.getenv("SUPERVISOR_TOKEN", "")
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    async def discover(self) -> dict[str, Any]:
        if not self.token:
            return self._unavailable("Supervisor API token is unavailable")

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "MediaHub/0.6.2",
                },
            ) as client:
                response = await client.get("/addons")
                response.raise_for_status()
                addons = self._extract_addons(response.json())
        except httpx.TimeoutException:
            return self._unavailable("Supervisor API request timed out")
        except httpx.HTTPStatusError as error:
            return self._unavailable(f"Supervisor API returned HTTP {error.response.status_code}")
        except httpx.RequestError:
            return self._unavailable("Unable to reach the Supervisor API")
        except (KeyError, TypeError, ValueError):
            return self._unavailable("Supervisor API returned an unexpected response")

        return {
            "available": True,
            "services": [self._match_service(service, addons) for service in SERVICES],
        }

    @staticmethod
    def _extract_addons(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ValueError("Invalid Supervisor response")
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("addons"), list):
            raise ValueError("Missing add-on list")
        return [addon for addon in data["addons"] if isinstance(addon, dict)]

    @classmethod
    def _match_service(
        cls,
        service: ServiceDefinition,
        addons: list[dict[str, Any]],
    ) -> dict[str, Any]:
        matches = [addon for addon in addons if cls._matches(service, addon)]
        if not matches:
            return {"name": service.name, "detected": False}

        addon = max(matches, key=lambda candidate: cls._match_score(service, candidate))
        slug = str(addon.get("slug", "")).strip()
        state = str(addon.get("state", "unknown"))
        hostname = slug.replace("_", "-")
        return {
            "name": service.name,
            "detected": True,
            "running": state == "started",
            "suggested_url": f"http://{hostname}:{service.port}",
            "addon": {
                "slug": slug,
                "name": str(addon.get("name", service.name.title())),
                "state": state,
                "version": str(addon.get("version", addon.get("installed", ""))),
            },
        }

    @staticmethod
    def _normalise(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()

    @classmethod
    def _matches(cls, service: ServiceDefinition, addon: dict[str, Any]) -> bool:
        haystack = " ".join(
            cls._normalise(addon.get(field, ""))
            for field in ("slug", "name", "description")
        )
        return any(alias in haystack for alias in service.aliases)

    @classmethod
    def _match_score(cls, service: ServiceDefinition, addon: dict[str, Any]) -> int:
        name = cls._normalise(addon.get("name", ""))
        slug = cls._normalise(addon.get("slug", ""))
        score = 0
        if name == service.name:
            score += 10
        if slug.endswith(service.name):
            score += 5
        if str(addon.get("state", "")) == "started":
            score += 2
        return score

    @staticmethod
    def _unavailable(message: str) -> dict[str, Any]:
        return {
            "available": False,
            "message": message,
            "services": [
                {"name": service.name, "detected": False} for service in SERVICES
            ],
        }
