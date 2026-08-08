from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from mediahub.app.settings import (
    load_options,
    normalise_service_url,
    public_integration_settings,
    save_integration_settings,
)


class SettingsTests(unittest.TestCase):
    def test_runtime_settings_override_addon_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            options_file = root / "options.json"
            settings_file = root / "settings.json"
            options_file.write_text(
                json.dumps({"integrations": {"radarr_url": "http://old-radarr:7878"}}),
                encoding="utf-8",
            )
            settings_file.write_text(
                json.dumps({"integrations": {"radarr_url": "http://new-radarr:7878"}}),
                encoding="utf-8",
            )

            options = load_options(options_file, settings_file)

            self.assertEqual(options["integrations"]["radarr_url"], "http://new-radarr:7878")
            self.assertEqual(options["storage"]["minimum_free_gb"], 50)

    def test_settings_are_saved_atomically_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.json"

            save_integration_settings(
                {
                    "prowlarr_url": "http://local-prowlarr:9696/",
                    "prowlarr_api_key": "secret-key",
                },
                settings_file=settings_file,
            )

            payload = json.loads(settings_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["integrations"]["prowlarr_url"], "http://local-prowlarr:9696")
            self.assertEqual(payload["integrations"]["prowlarr_api_key"], "secret-key")
            self.assertEqual(stat.S_IMODE(settings_file.stat().st_mode), 0o600)
            self.assertEqual(list(settings_file.parent.glob(".settings.json.*")), [])

    def test_blank_secret_preserves_existing_value_unless_explicitly_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.json"
            save_integration_settings(
                {"tmdb_api_key": "existing-secret"},
                settings_file=settings_file,
            )

            save_integration_settings(
                {"tmdb_api_key": ""},
                settings_file=settings_file,
            )
            preserved = json.loads(settings_file.read_text(encoding="utf-8"))
            self.assertEqual(preserved["integrations"]["tmdb_api_key"], "existing-secret")

            save_integration_settings(
                {},
                clear_secrets=["tmdb_api_key"],
                settings_file=settings_file,
            )
            cleared = json.loads(settings_file.read_text(encoding="utf-8"))
            self.assertEqual(cleared["integrations"]["tmdb_api_key"], "")

    def test_public_settings_never_return_credentials(self) -> None:
        public = public_integration_settings(
            {
                "integrations": {
                    "tmdb_api_key": "tmdb-secret",
                    "radarr_url": "http://radarr:7878",
                    "radarr_api_key": "radarr-secret",
                    "sonarr_url": "http://user:embedded-secret@sonarr:8989",
                    "qbittorrent_username": "mediahub",
                    "qbittorrent_auth_method": "api_key",
                    "qbittorrent_api_key": "qbt_secret",
                    "qbittorrent_password": "password-secret",
                }
            }
        )

        self.assertTrue(public["tmdb"]["api_key_set"])
        self.assertTrue(public["radarr"]["api_key_set"])
        self.assertTrue(public["qbittorrent"]["password_set"])
        self.assertTrue(public["qbittorrent"]["api_key_set"])
        self.assertEqual(public["qbittorrent"]["auth_method"], "api_key")
        self.assertEqual(public["sonarr"]["url"], "")
        self.assertNotIn("tmdb-secret", str(public))
        self.assertNotIn("radarr-secret", str(public))
        self.assertNotIn("password-secret", str(public))
        self.assertNotIn("qbt_secret", str(public))
        self.assertNotIn("embedded-secret", str(public))

    def test_service_url_validation_rejects_embedded_credentials(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be embedded"):
            normalise_service_url("http://user:password@radarr:7878")

    def test_radarr_quality_profile_must_be_a_valid_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "valid ID"):
                save_integration_settings(
                    {"radarr_quality_profile_id": "not-an-id"},
                    settings_file=Path(directory) / "settings.json",
                )

    def test_qbittorrent_authentication_method_must_be_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "authentication method"):
                save_integration_settings(
                    {"qbittorrent_auth_method": "unsupported"},
                    settings_file=Path(directory) / "settings.json",
                )


if __name__ == "__main__":
    unittest.main()
