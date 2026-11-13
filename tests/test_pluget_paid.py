import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pluget_paid import PluginInstallError, install_plugin, scan_for_malware


class PluginInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.jar = self.root / "ExamplePlugin.jar"
        with zipfile.ZipFile(self.jar, "w") as archive:
            archive.writestr("plugin.yml", "name: ExamplePlugin\nversion: 1.0\n")
            archive.writestr("ExamplePlugin.class", b"placeholder")
        self.plugins_dir = self.root / "server" / "plugins"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_installs_valid_plugin_after_clean_scan(self):
        with patch("pluget_paid.scan_for_malware") as scan:
            installed = install_plugin(self.jar, self.plugins_dir)
        scan.assert_called_once_with(self.jar.resolve())
        self.assertEqual(installed.read_bytes(), self.jar.read_bytes())

    def test_refuses_to_replace_without_opt_in(self):
        with patch("pluget_paid.scan_for_malware"):
            install_plugin(self.jar, self.plugins_dir)
            with self.assertRaises(PluginInstallError):
                install_plugin(self.jar, self.plugins_dir)

    def test_overwrite_replaces_existing_file(self):
        with patch("pluget_paid.scan_for_malware"):
            install_plugin(self.jar, self.plugins_dir)
            self.jar.write_bytes(b"not a jar")
            # Invalid input is rejected before any existing installation is modified.
            with self.assertRaises(PluginInstallError):
                install_plugin(self.jar, self.plugins_dir, overwrite=True)

    def test_rejects_non_plugin_jar(self):
        invalid = self.root / "other.jar"
        with zipfile.ZipFile(invalid, "w") as archive:
            archive.writestr("readme.txt", "not a plugin")
        with patch("pluget_paid.scan_for_malware") as scan:
            with self.assertRaises(PluginInstallError):
                install_plugin(invalid, self.plugins_dir)
        scan.assert_not_called()
        self.assertFalse(self.plugins_dir.exists())

    def test_rejects_non_jar_file(self):
        invalid = self.root / "plugin.txt"
        invalid.write_text("nope")
        with patch("pluget_paid.scan_for_malware"):
            with self.assertRaises(PluginInstallError):
                install_plugin(invalid, self.plugins_dir)

    @patch("pluget_paid.subprocess.run")
    @patch("pluget_paid.shutil.which", return_value="/usr/bin/clamscan")
    def test_clamav_clean_result(self, _which, run):
        run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        scan_for_malware(self.jar)
        self.assertEqual(run.call_args.args[0][-1], str(self.jar))

    @patch("pluget_paid.subprocess.run")
    @patch("pluget_paid.shutil.which", return_value="/usr/bin/clamscan")
    def test_clamav_detection_blocks_install(self, _which, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="ExamplePlugin.jar: Test.Malware FOUND", stderr=""
        )
        with patch("pluget_paid.scan_for_malware", side_effect=PluginInstallError("Malware detected")):
            with self.assertRaises(PluginInstallError):
                install_plugin(self.jar, self.plugins_dir)
        self.assertFalse(self.plugins_dir.exists())

    @patch("pluget_paid.shutil.which", return_value=None)
    def test_missing_clamav_fails_closed(self, _which):
        with self.assertRaisesRegex(PluginInstallError, "install ClamAV"):
            scan_for_malware(self.jar)

    @patch("pluget_paid.subprocess.run", side_effect=subprocess.TimeoutExpired("clamscan", 120))
    @patch("pluget_paid.shutil.which", return_value="/usr/bin/clamscan")
    def test_scan_timeout_blocks_install(self, _which, _run):
        with self.assertRaisesRegex(PluginInstallError, "timed out"):
            scan_for_malware(self.jar)


if __name__ == "__main__":
    unittest.main()
