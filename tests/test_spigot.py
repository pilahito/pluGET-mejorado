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
                install_spigot_resource("../123", self.plugins_dir)
        request.assert_not_called()

    def test_fetches_resource_and_downloads_jar_for_scanned_install(self):
        jar_bytes = make_plugin_jar()
        responses = [
            FakeResponse(json.dumps({"name": "Example Plugin"}).encode()),
            FakeResponse(jar_bytes),
        ]
        with patch("spigot._request", side_effect=responses) as request, \
             patch("spigot.install_plugin", return_value=self.plugins_dir / "installed.jar") as install:
            result = install_spigot_resource("1234", self.plugins_dir)

        self.assertEqual(result, self.plugins_dir / "installed.jar")
        self.assertEqual(request.call_count, 2)
        downloaded_path = install.call_args.args[0]
        self.assertTrue(downloaded_path.name.endswith("-spigot-1234.jar"))
        self.assertEqual(downloaded_path.read_bytes(), jar_bytes)
        self.assertEqual(install.call_args.args[1], self.plugins_dir)

    def test_rejects_invalid_spiget_metadata(self):
        with patch("spigot._request", return_value=FakeResponse(b"[]")):
            with self.assertRaisesRegex(PluginInstallError, "invalid resource information"):
                install_spigot_resource("1234", self.plugins_dir)


if __name__ == "__main__":
    unittest.main()
