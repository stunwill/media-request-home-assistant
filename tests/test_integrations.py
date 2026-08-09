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

    def test_qbittorrent_api_key_does_not_require_password_credentials(self) -> None:
        configured = IntegrationConfig(
            name="qbittorrent",
            url="http://qbittorrent:8080",
            api_key="qbt_example",
            auth_method="api_key",
        )
        self.assertTrue(configured.configured)


class IntegrationTesterTests(unittest.IsolatedAsyncioTestCase):
    async def test_not_configured_does_not_make_network_request(self) -> None:
        async def fail_if_called(request: httpx.Request) -> httpx.Response:
            self.fail(f"Unexpected request: {request.url}")

        tester = IntegrationTester(transport=httpx.MockTransport(fail_if_called))
        result = await tester.test(IntegrationConfig(name="tmdb"))
        self.assertEqual(result, {"name": "tmdb", "status": "not_configured", "configured": False})

    async def assert_arr_connection(
        self,
        *,
        name: str,
        url: str,
        expected_path: str,
    ) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, expected_path)
            self.assertEqual(request.headers["X-Api-Key"], "secret")
            return httpx.Response(200, json={"appName": name.title(), "version": "1.2.3"})

        tester = IntegrationTester(transport=httpx.MockTransport(handler))
        result = await tester.test(
            IntegrationConfig(name=name, url=url, api_key="secret")
        )
        self.assertEqual(result["status"], "connected")
        self.assertEqual(result["details"], {"app_name": name.title(), "version": "1.2.3"})
        self.assertNotIn("secret", str(result))

    async def test_prowlarr_connection_uses_api_v1(self) -> None:
        await self.assert_arr_connection(
            name="prowlarr",
            url="http://prowlarr:9696/",
            expected_path="/api/v1/system/status",
        )

    async def test_radarr_connection_uses_api_v3(self) -> None:
        await self.assert_arr_connection(
            name="radarr",
            url="http://radarr:7878/",
            expected_path="/api/v3/system/status",
        )

    async def test_sonarr_connection_uses_api_v3(self) -> None:
        await self.assert_arr_connection(
            name="sonarr",
            url="http://sonarr:8989/",
            expected_path="/api/v3/system/status",
        )

    async def test_prowlarr_http_error_is_sanitised(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v1/system/status")
            return httpx.Response(
                404,
                text="API key secret was rejected by an unknown endpoint",
                request=request,
            )

        tester = IntegrationTester(transport=httpx.MockTransport(handler))
        result = await tester.test(
            IntegrationConfig(
                name="prowlarr",
                url="http://prowlarr:9696",
                api_key="secret",
            )
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["message"], "Service returned HTTP 404")
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

    async def test_qbittorrent_password_auth_verifies_version_not_login_body(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.headers["Origin"], "http://qbittorrent:8080")
            self.assertEqual(request.headers["Referer"], "http://qbittorrent:8080/")
            if request.url.path == "/api/v2/auth/login":
                return httpx.Response(
                    200,
                    text="Authentication bypassed",
                    headers={"Set-Cookie": "SID=session; path=/"},
                )
            if request.url.path == "/api/v2/app/version":
                self.assertEqual(request.headers.get("Cookie"), "SID=session")
                return httpx.Response(200, text="v5.2.0")
            self.fail(f"Unexpected qBittorrent request: {request.url}")

        tester = IntegrationTester(transport=httpx.MockTransport(handler))
        result = await tester.test(
            IntegrationConfig(
                name="qbittorrent",
                url="http://qbittorrent:8080",
                username="mediahub",
                password="secret",
            )
        )

        self.assertEqual(result["status"], "connected")
        self.assertEqual(result["details"], {"version": "v5.2.0"})
        self.assertEqual([request.url.path for request in requests], [
            "/api/v2/auth/login",
            "/api/v2/app/version",
        ])

    async def test_qbittorrent_api_key_uses_bearer_auth_without_login(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v2/app/version")
            self.assertEqual(request.headers["Authorization"], "Bearer qbt_example")
            return httpx.Response(200, text="v5.2.0")

        tester = IntegrationTester(transport=httpx.MockTransport(handler))
        result = await tester.test(
            IntegrationConfig(
                name="qbittorrent",
                url="http://qbittorrent:8080",
                api_key="qbt_example",
                auth_method="api_key",
            )
        )

        self.assertEqual(result["status"], "connected")
        self.assertEqual(result["details"], {"version": "v5.2.0"})

    async def test_qbittorrent_rejected_password_is_an_authentication_failure(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/auth/login":
                return httpx.Response(200, text="Fails.")
            if request.url.path == "/api/v2/app/version":
                return httpx.Response(403)
            self.fail(f"Unexpected qBittorrent request: {request.url}")

        tester = IntegrationTester(transport=httpx.MockTransport(handler))
        result = await tester.test(
            IntegrationConfig(
                name="qbittorrent",
                url="http://qbittorrent:8080",
                username="mediahub",
                password="wrong",
            )
        )

        self.assertEqual(result["status"], "authentication_failed")
        self.assertEqual(result["message"], "Service returned HTTP 403")


if __name__ == "__main__":
    unittest.main()
