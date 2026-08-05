from __future__ import annotations

import unittest

import httpx

from mediahub.app.discovery import SupervisorDiscovery


class SupervisorDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_token_returns_safe_unavailable_result(self) -> None:
        discovery = SupervisorDiscovery(token="")
        result = await discovery.discover()

        self.assertFalse(result["available"])
        self.assertEqual(len(result["services"]), 4)
        self.assertNotIn("token", str(result).lower().replace("token is unavailable", ""))

    async def test_installed_services_are_matched_and_receive_internal_urls(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/addons")
            self.assertEqual(request.headers["Authorization"], "Bearer supervisor-secret")
            return httpx.Response(
                200,
                json={
                    "data": {
                        "addons": [
                            {
                                "slug": "5c53de3b_prowlarr",
                                "name": "Prowlarr",
                                "state": "started",
                                "version": "2.0.5",
                            },
                            {
                                "slug": "local_radarr",
                                "name": "Radarr",
                                "state": "stopped",
                                "version": "5.1.0",
                            },
                            {
                                "slug": "abc123_qbittorrent",
                                "name": "qBittorrent",
                                "state": "started",
                                "version": "5.0.4",
                            },
                        ]
                    }
                },
            )

        discovery = SupervisorDiscovery(
            token="supervisor-secret",
            transport=httpx.MockTransport(handler),
        )
        result = await discovery.discover()

        self.assertTrue(result["available"])
        services = {service["name"]: service for service in result["services"]}
        self.assertEqual(
            services["prowlarr"]["suggested_url"],
            "http://5c53de3b-prowlarr:9696",
        )
        self.assertTrue(services["prowlarr"]["running"])
        self.assertEqual(services["radarr"]["suggested_url"], "http://local-radarr:7878")
        self.assertFalse(services["radarr"]["running"])
        self.assertFalse(services["sonarr"]["detected"])
        self.assertNotIn("supervisor-secret", str(result))

    async def test_supervisor_error_does_not_expose_response_body(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                text="Bearer supervisor-secret was rejected",
                request=request,
            )

        discovery = SupervisorDiscovery(
            token="supervisor-secret",
            transport=httpx.MockTransport(handler),
        )
        result = await discovery.discover()

        self.assertFalse(result["available"])
        self.assertEqual(result["message"], "Supervisor API returned HTTP 403")
        self.assertNotIn("supervisor-secret", str(result))


if __name__ == "__main__":
    unittest.main()
