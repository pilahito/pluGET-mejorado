import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pluget_paid import PluginInstallError, build_parser, main, write_stage_report
from spigot import is_prerelease_version
from spigot_updates import update_configured_spigot, update_spigot_resource


def plugin_jar(version="1.0"):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("plugin.yml", f"name: Example\nversion: {version}\n")
    return data.getvalue()


class PrereleaseTests(unittest.TestCase):
    def test_marks_prerelease_names(self):
        for name in ["2.0.0-beta3", "2.0-SNAPSHOT", "3.1 RC2", "1.0 Pre-Release", "1.2.3-alpha", "4.0-dev"]:
            self.assertTrue(is_prerelease_version(name), name)

    def test_keeps_stable_names(self):
        for name in ["1.2.3", "2.22.0", "5.4", "Stable 3.0", "1.2 Prestige", "2.0 Devotion", ""]:
            self.assertFalse(is_prerelease_version(name), name)


class StageTests(unittest.TestCase):
    def test_parser_accepts_stage_dir_without_plugins_dir(self):
        args = build_parser().parse_args(["--spigot", "9089", "--minecraft-version", "1.21.4", "--stage-dir", "/tmp/x"])
        self.assertIsNone(args.plugins_dir)
        self.assertEqual(args.stage_dir, Path("/tmp/x"))

    def test_stage_dir_rejected_for_local_jar(self):
        with self.assertRaises(SystemExit):
            main(["/tmp/a.jar", "--plugins-dir", "/tmp/p", "--stage-dir", "/tmp/s"])

    def test_report_has_hash_per_jar(self):
        with tempfile.TemporaryDirectory() as tmp:
            jar = Path(tmp) / "Demo-1.0.jar"
            jar.write_bytes(b"PK-demo")
            report_path = write_stage_report(jar, "9089", Path(tmp))
            data = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report_path.name, "Demo-1.0.jar.informe.json")
            self.assertEqual(data["spigot_id"], "9089")
            self.assertEqual(len(data["sha256"]), 64)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plugins = self.root / "plugins"
        self.plugins.mkdir()
        self.stage = self.root / "stage"
        self.stage.mkdir()
        self.jar = plugin_jar("2.0")

    def tearDown(self):
        self.tmp.cleanup()

    def fake_download(self, _rid, destination):
        destination.write_bytes(self.jar)

    @patch("spigot_updates.install_plugin")
    @patch("spigot_updates._download_resource")
    @patch("spigot_updates._fetch_resource", return_value={"name": "Example", "testedVersions": ["1.21"]})
    def test_uses_installed_name_to_avoid_duplicates(self, _fetch, download, install):
        download.side_effect = self.fake_download
        install.return_value = self.plugins / "Example-1.0.jar"
        (self.plugins / "Example-1.0.jar").write_bytes(plugin_jar("1.0"))
        update_spigot_resource("123", self.plugins, "1.21.4", filename="Example-1.0.jar")
        candidate = install.call_args.args[0]
        self.assertEqual(candidate.name, "Example-1.0.jar")

    @patch("spigot_updates.install_plugin")
    @patch("spigot_updates._download_resource")
    @patch("spigot_updates._fetch_resource", return_value={"name": "Example", "testedVersions": ["1.21"]})
    def test_stage_writes_to_stage_dir_not_plugins(self, _fetch, download, install):
        download.side_effect = self.fake_download
        install.return_value = self.stage / "Example-spigot-123.jar"
        status, _ = update_spigot_resource("123", self.plugins, "1.21.4", stage_dir=self.stage)
        self.assertEqual(status, "staged")
        self.assertEqual(install.call_args.args[1], self.stage.resolve())

    @patch("spigot_updates._download_resource")
    @patch("spigot_updates._latest_version_name", return_value="3.0-beta2")
    @patch("spigot_updates._fetch_resource", return_value={"name": "Example", "testedVersions": ["1.21"]})
    def test_stable_only_skips_prerelease_without_downloading(self, _fetch, _latest, download):
        status, path = update_spigot_resource("123", self.plugins, "1.21.4", stable_only=True)
        self.assertTrue(status.startswith("skipped"))
        self.assertIsNone(path)
        download.assert_not_called()

    def test_rejects_path_in_archivo(self):
        with patch("spigot_updates._fetch_resource", return_value={"name": "Example", "testedVersions": ["1.21"]}):
            with self.assertRaises(PluginInstallError):
                update_spigot_resource("123", self.plugins, "1.21.4", filename="../evil.jar")

    @patch("spigot_updates.update_spigot_resource", return_value=("updated", None))
    def test_config_accepts_ids_and_objects(self, update):
        config = self.root / "c.json"
        config.write_text(json.dumps({
            "minecraft_version": "1.21.4", "plugins_dir": str(self.plugins), "solo_estables": True,
            "resources": [28140, {"id": 9089, "archivo": "EssentialsX.jar"}],
        }))
        update_configured_spigot(config)
        calls = update.call_args_list
        self.assertEqual(calls[0].args[0], "28140")
        self.assertIsNone(calls[0].kwargs["filename"])
        self.assertEqual(calls[1].kwargs["filename"], "EssentialsX.jar")
        self.assertTrue(calls[1].kwargs["stable_only"])


if __name__ == "__main__":
    unittest.main()
