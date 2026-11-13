import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from paper_server import detect_paper_version, download_latest_paper, get_latest_paper_build
from pluget_paid import PluginInstallError


class FakeResponse:
    def __init__(self, content):
        self.buffer = io.BytesIO(content)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.buffer.close()

    def read(self, size=-1):
        return self.buffer.read(size)


class PaperServerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_server_jar(self, version):
        path = self.root / "server.jar"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("version.json", json.dumps({"id": version}))
        return path

    def test_detects_minecraft_version_from_version_json(self):
        jar = self.make_server_jar("1.21.4")
        self.assertEqual(detect_paper_version(jar), "1.21.4")

    def test_returns_latest_paper_build_from_api(self):
        responses = [
            {"versions": ["1.21.3", "1.21.4"]},
            {"builds": [{"build": 1}, {"build": 2}]},
            {"downloads": {"application": {"name": "paper.jar", "sha256": "a" * 64}}},
        ]
        with patch("paper_server._get_json", side_effect=responses) as get_json:
            result = get_latest_paper_build()
        self.assertEqual(result, ("1.21.4", 2, "paper.jar", "a" * 64))
        self.assertEqual(get_json.call_count, 3)

    def test_refuses_to_replace_existing_jar_without_overwrite(self):
        jar = self.make_server_jar("1.20.4")
        with patch("paper_server.get_latest_paper_build", return_value=("1.21.4", 10, "paper.jar", "a" * 64)):
            with self.assertRaisesRegex(PluginInstallError, "pass --overwrite"):
                download_latest_paper(jar)
        self.assertEqual(detect_paper_version(jar), "1.20.4")

    def test_download_verifies_checksum_and_preserves_backup(self):
        jar = self.make_server_jar("1.20.4")
        new_jar_bytes = io.BytesIO()
        with zipfile.ZipFile(new_jar_bytes, "w") as archive:
            archive.writestr("version.json", json.dumps({"id": "1.21.4"}))
        payload = new_jar_bytes.getvalue()
        checksum = hashlib.sha256(payload).hexdigest()
        api_responses = [
            {"versions": ["1.21.4"]},
            {"builds": [{"build": 10}]},
            {"downloads": {"application": {"name": "paper-1.21.4-10.jar", "sha256": checksum}}},
        ]
        with patch("paper_server._get_json", side_effect=api_responses), \
             patch("paper_server.urllib.request.urlopen", return_value=FakeResponse(payload)):
            installed, current, latest, build = download_latest_paper(jar, overwrite=True)
        self.assertEqual((installed, current, latest, build), (jar, "1.20.4", "1.21.4", 10))
        self.assertEqual(detect_paper_version(jar), "1.21.4")
        self.assertEqual(detect_paper_version(jar.with_name("server.jar.previous")), "1.20.4")

    def test_checksum_mismatch_does_not_replace_server(self):
        jar = self.make_server_jar("1.20.4")
        payload = b"not the API checksum"
        with patch("paper_server.get_latest_paper_build", return_value=("1.21.4", 10, "paper.jar", "0" * 64)), \
             patch("paper_server.urllib.request.urlopen", return_value=FakeResponse(payload)):
            with self.assertRaisesRegex(PluginInstallError, "checksum mismatch"):
                download_latest_paper(jar, overwrite=True)
        self.assertEqual(detect_paper_version(jar), "1.20.4")


if __name__ == "__main__":
    unittest.main()
