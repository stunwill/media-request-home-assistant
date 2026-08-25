from __future__ import annotations

from typing import Literal

from pydantic import Field

from . import main, plex_integration, plex_library, settings

app = plex_integration.app

PlexIntegrationField = Literal[
    "tmdb_api_key",
    "prowlarr_url",
    "prowlarr_api_key",
    "radarr_url",
    "radarr_api_key",
    "radarr_root_folder_path",
    "radarr_quality_profile_id",
    "sonarr_url",
    "sonarr_api_key",
    "qbittorrent_url",
    "qbittorrent_auth_method",
    "qbittorrent_api_key",
    "qbittorrent_username",
    "qbittorrent_password",
    "plex_url",
    "plex_token",
    "plex_library_key",
    "plex_machine_identifier",
]
PlexSecretField = Literal[
    "tmdb_api_key",
    "prowlarr_api_key",
    "radarr_api_key",
    "sonarr_api_key",
    "qbittorrent_api_key",
    "qbittorrent_password",
    "plex_token",
]


class PlexIntegrationSettingsUpdate(main.BaseModel):
    updates: dict[PlexIntegrationField, str] = Field(default_factory=dict)
    clear_secrets: list[PlexSecretField] = Field(default_factory=list)


async def integration_status_with_plex(_: main.Manager) -> dict:
    tester = main.IntegrationTester()
    services = await tester.test_all(main.integration_configs(main.load_options()))
    services.append(await plex_integration.plex_status_payload())
    return {
        "services": services,
        "connected": sum(service["status"] == "connected" for service in services),
        "configured": sum(bool(service.get("configured")) for service in services),
        "total": len(services),
    }


async def setup_payload_with_plex() -> dict:
    payload = await main.setup_payload()
    plex_status = await plex_integration.plex_status_payload()
    services = [item for item in payload["connections"]["services"] if item.get("name") != "plex"]
    services.append(plex_status)
    payload["connections"] = {
        "services": services,
        "connected": sum(service["status"] == "connected" for service in services),
        "configured": sum(bool(service.get("configured")) for service in services),
        "total": len(services),
    }
    payload["settings"] = settings.public_integration_settings(main.load_options())
    return payload


async def get_setup_with_plex(_: main.Administrator) -> dict:
    return await setup_payload_with_plex()


async def update_integration_settings_with_plex(
    payload: PlexIntegrationSettingsUpdate,
    principal: main.Administrator,
) -> dict:
    if any(len(value) > 2048 for value in payload.updates.values()):
        raise main.HTTPException(status_code=422, detail="Integration values must be 2048 characters or fewer")
    try:
        settings.save_integration_settings(dict(payload.updates), clear_secrets=payload.clear_secrets)
    except (OSError, ValueError) as error:
        raise main.HTTPException(status_code=422, detail=str(error)) from error
    plex_library.PLEX_CACHE.clear()
    with main.connect_db() as db:
        main.record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="integration_settings_updated",
            request_id=None,
            details={
                "updated_fields": sorted(payload.updates),
                "cleared_secret_fields": sorted(payload.clear_secrets),
            },
        )
        db.commit()
    return await setup_payload_with_plex()


plex_integration.rich_details.runtime.enhanced_main._replace_route(
    "/api/integrations/status", "GET", integration_status_with_plex
)
plex_integration.rich_details.runtime.enhanced_main._replace_route(
    "/api/setup", "GET", get_setup_with_plex
)
plex_integration.rich_details.runtime.enhanced_main._replace_route(
    "/api/setup/integrations", "PUT", update_integration_settings_with_plex
)
