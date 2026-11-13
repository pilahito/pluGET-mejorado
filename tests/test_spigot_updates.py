import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pluget_paid import PluginInstallError
from spigot_updates import update_configured_spigot, update_spigot_resource


class SpigotUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.plugins = self.root / "plugins"
        self.plugins.mkdir()
        self.jar_bytes = self.make_plugin_jar("1.0")

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def make_plugin_jar(version):
        import io
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("plugin.yml", f"name: Example\nversion: {version}\n")
        return data.getvalue()

    def fake_download(self, _resource_id, destination):
        destination.write_bytes(self.jar_bytes)

    @patch("spigot_updates.install_plugin")
    @patch("spigot_updates._download_resource")
    @patch("spigot_updates._fetch_resource", return_value={"name": "Example", "testedVersions": ["1.21"]})
    def test_installs_first_version(self, _fetch, download, install):
        install.return_value = self.plugins / "Example-spigot-123.jar"
        with patch.object(self, "fake_download", side_effect=self.fake_download):
            download.side_effect = self.fake_download
            status, path = update_spigot_resource("123", self.plugins, "1.21.4")
        self.assertEqual(status, "updated")
        self.assertEqual(path, install.return_value)
        install.assert_called_once()
        self.assertTrue(install.call_args.kwargs["overwrite"])

    @patch("spigot_updates._download_resource")
    @patch("spigot_updates._fetch_resource", return_value={"name": "Example", "testedVersions": ["1.21"]})
    def test_skips_identical_jar(self, _fetch, download):
        destination = self.plugins / "Example-spigot-123.jar"
        destination.write_bytes(self.jar_bytes)
        download.side_effect = self.fake_download
        with patch("spigot_updates.install_plugin") as install:
            status, path = update_spigot_resource("123", self.plugins, "1.21.4")
        self.assertEqual((status, path), ("unchanged", destination))
        install.assert_not_called()

    @patch("spigot_updates._fetch_resource", return_value={"name": "Example", "testedVersions": ["1.21"]})
    def test_rejects_version_mismatch_before_download(self, _fetch):
        with patch("spigot_updates._download_resource") as download:
            with self.assertRaisesRegex(PluginInstallError, "not marked as tested"):
                update_spigot_resource("123", self.plugins, "1.20.4")
        download.assert_not_called()

    def test_reads_config_and_updates_resources(self):
        config = self.root / "spigot-updates.json"
        config.write_text(json.dumps({
            "minecraft_version": "1.21.4",
            "plugins_dir": str(self.plugins),
            "resources": ["123", "456"],
        }))
        with patch("spigot_updates.update_spigot_resource", side_effect=[("updated", self.plugins / "a.jar"), ("unchanged", self.plugins / "b.jar")]) as update:
            result = update_configured_spigot(config)
        self.assertEqual([row[1] for row in result], ["updated", "unchanged"])
        self.assertEqual(update.call_count, 2)

    def test_missing_config_is_rejected(self):
        with self.assertRaisesRegex(PluginInstallError, "Could not read update config"):
            update_configured_spigot(self.root / "missing.json")


if __name__ == "__main__":
    unittest.main()
