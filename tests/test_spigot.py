import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pluget_paid import PluginInstallError
from spigot import install_spigot_resource


class FakeResponse:
    def __init__(self, content):
        self.buffer = io.BytesIO(content)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.buffer.close()

    def read(self, size=-1):
        return self.buffer.read(size)


def make_plugin_jar():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("plugin.yml", "name: Example\nversion: 1.0\n")
    return output.getvalue()


class SpigotIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.plugins_dir = Path(self.temp_dir.name) / "plugins"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rejects_non_numeric_id_without_network_request(self):
        with patch("spigot._request") as request:
            with self.assertRaisesRegex(PluginInstallError, "only digits"):
                install_spigot_resource("../123", self.plugins_dir, minecraft_version="1.21.4")
        request.assert_not_called()

    def test_requires_minecraft_version_before_network_request(self):
        with patch("spigot._request") as request:
            with self.assertRaisesRegex(PluginInstallError, "Minecraft version is required"):
                install_spigot_resource("1234", self.plugins_dir)
        request.assert_not_called()

    def test_paper_server_jar_version_is_detected(self):
        jar = Path(self.temp_dir.name) / "paper.jar"
        with patch("spigot.detect_paper_version", return_value="1.21.4") as detect, \
             patch("spigot._fetch_resource", return_value={"name": "Example", "testedVersions": ["1.21"]}), \
             patch("spigot._download_resource"), \
             patch("spigot.install_plugin", return_value=self.plugins_dir / "plugin.jar"):
            install_spigot_resource("1234", self.plugins_dir, server_jar=jar)
        detect.assert_called_once_with(jar)

    def test_downloads_only_if_server_version_is_marked_tested(self):
        jar_bytes = make_plugin_jar()
        responses = [
            FakeResponse(json.dumps({"name": "Example Plugin", "testedVersions": ["1.21"]}).encode()),
            FakeResponse(jar_bytes),
        ]
        with patch("spigot._request", side_effect=responses) as request, \
             patch("spigot.install_plugin", return_value=self.plugins_dir / "installed.jar") as install:
            result = install_spigot_resource(
                "1234", self.plugins_dir, minecraft_version="1.21.4"
            )
        self.assertEqual(result, self.plugins_dir / "installed.jar")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(install.call_args.args[1], self.plugins_dir)

    def test_rejects_incompatible_version_before_download(self):
        with patch("spigot._request", return_value=FakeResponse(
            json.dumps({"name": "Example", "testedVersions": ["1.20.4"]}).encode()
        )) as request:
            with self.assertRaisesRegex(PluginInstallError, "not marked as tested"):
                install_spigot_resource("1234", self.plugins_dir, minecraft_version="1.21.4")
        self.assertEqual(request.call_count, 1)

    def test_rejects_missing_compatibility_metadata(self):
        with patch("spigot._request", return_value=FakeResponse(
            json.dumps({"name": "Example"}).encode()
        )) as request:
            with self.assertRaisesRegex(PluginInstallError, "compatibility cannot be checked"):
                install_spigot_resource("1234", self.plugins_dir, minecraft_version="1.21.4")
        self.assertEqual(request.call_count, 1)

    def test_rejects_invalid_spiget_metadata(self):
        with patch("spigot._request", return_value=FakeResponse(b"[]")):
            with self.assertRaisesRegex(PluginInstallError, "invalid resource information"):
                install_spigot_resource("1234", self.plugins_dir, minecraft_version="1.21.4")


if __name__ == "__main__":
    unittest.main()
