from __future__ import annotations

import unittest

import httpx

from mediahub.app.integrations import IntegrationConfig, IntegrationTester, integration_configs


class IntegrationConfigTests(unittest.TestCase):
    def test_all_expected_services_are_created(self) -> None:
        configs = integration_configs({"integrations": {}})
        self.assertEqual(
            [config.name for config in configs],
            ["tmdb", "prowlarr", "radarr", "sonarr", "qbittorrent"],
        )
        self.assertTrue(all(not config.configured for config in configs))

    def test_qbittorrent_requires_all_credentials(self) -> None:
        incomplete = IntegrationConfig(
            name="qbittorrent", url="http://qbittorrent:8080", username="mediahub"
        )
        self.assertFalse(incomplete.configured)


class IntegrationTesterTests(unittest.IsolatedAsyncioTestCase):
    async def test_not_configured_does_not_make_network_request(self) -> None:
        async def fail_if_called(request: httpx.Request) -> httpx.Response:
            self.fail(f"Unexpected request: {request.url}")

        tester = IntegrationTester(transport=httpx.MockTransport(fail_if_called))
        result = await tester.test(IntegrationConfig(name="tmdb"))
        self.assertEqual(result, {"name": "tmdb", "status": "not_configured", "configured": False})

    async def test_arr_connection_returns_sanitised_version_details(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v3/system/status")
            self.assertEqual(request.headers["X-Api-Key"], "secret")
            return httpx.Response(200, json={"appName": "Prowlarr", "version": "1.2.3"})

        tester = IntegrationTester(transport=httpx.MockTransport(handler))
        result = await tester.test(
            IntegrationConfig(name="prowlarr", url="http://prowlarr:9696/", api_key="secret")
        )
        self.assertEqual(result["status"], "connected")
        self.assertEqual(result["details"], {"app_name": "Prowlarr", "version": "1.2.3"})
        self.assertNotIn("secret", str(result))

    async def test_authentication_failure_does_not_expose_response_body(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="API key secret was invalid", request=request)

        tester = IntegrationTester(transport=httpx.MockTransport(handler))
        result = await tester.test(
            IntegrationConfig(name="radarr", url="http://radarr:7878", api_key="secret")
        )
        self.assertEqual(result["status"], "authentication_failed")
        self.assertEqual(result["message"], "Service returned HTTP 401")
        self.assertNotIn("secret", str(result))


if __name__ == "__main__":
    unittest.main()
