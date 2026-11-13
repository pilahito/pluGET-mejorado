"""Check and download the latest stable Paper Minecraft server build."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from pluget_paid import PluginInstallError

PAPER_API = "https://api.papermc.io/v2"
USER_AGENT = "pluGET-mejorado/0.1 (Paper server updater)"
REQUEST_TIMEOUT = 30
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise PluginInstallError(f"Paper API returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginInstallError(f"Could not connect to the Paper API: {exc}") from exc
    if not isinstance(data, dict):
        raise PluginInstallError("Paper API returned an invalid response.")
    return data


def detect_paper_version(server_jar: Path) -> str | None:
    """Best-effort version detection from version.json or the JAR manifest."""
    if not server_jar.is_file():
        return None
    try:
        with zipfile.ZipFile(server_jar) as archive:
            for name in ("version.json", "META-INF/version.json"):
                try:
                    info = archive.getinfo(name)
                except KeyError:
                    continue
                if info.file_size > 1024 * 1024:
                    continue
                data = json.loads(archive.read(name).decode("utf-8"))
                for key in ("id", "name", "version", "minecraftVersion"):
                    value = data.get(key) if isinstance(data, dict) else None
                    if isinstance(value, str) and value.strip():
                        return value.strip()

            try:
                manifest_info = archive.getinfo("META-INF/MANIFEST.MF")
                if manifest_info.file_size <= 1024 * 1024:
                    manifest = archive.read(manifest_info).decode("utf-8", errors="replace")
                    for key in ("Implementation-Version", "Specification-Version", "Bundle-Version"):
                        match = re.search(rf"(?im)^{re.escape(key)}:\s*(.+?)\s*$", manifest)
                        if match:
                            return match.group(1).strip()
            except KeyError:
                pass
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError):
        return None
    return None


def get_latest_paper_build() -> tuple[str, int, str, str]:
    """Return latest stable Minecraft version, Paper build, filename and SHA-256."""
    project = _get_json(f"{PAPER_API}/projects/paper")
    versions = project.get("versions")
    if not isinstance(versions, list) or not versions:
        raise PluginInstallError("Paper API did not list any Minecraft versions.")

    version = versions[-1]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        raise PluginInstallError("Paper API returned an invalid Minecraft version.")
    builds_data = _get_json(f"{PAPER_API}/projects/paper/versions/{version}/builds")
    builds = builds_data.get("builds")
    if not isinstance(builds, list) or not builds:
        raise PluginInstallError(f"Paper API did not list builds for Minecraft {version}.")

    latest_build = builds[-1]
    if not isinstance(latest_build, dict) or not isinstance(latest_build.get("build"), int):
        raise PluginInstallError("Paper API returned invalid build information.")
    build_number = latest_build["build"]
    build_data = _get_json(
        f"{PAPER_API}/projects/paper/versions/{version}/builds/{build_number}"
    )
    application = build_data.get("downloads", {}).get("application", {})
    filename = application.get("name")
    sha256 = application.get("sha256")
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".jar"):
        raise PluginInstallError("Paper API returned an invalid server JAR filename.")
    if not isinstance(sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", sha256):
        raise PluginInstallError("Paper API did not provide a valid SHA-256 checksum.")
    return version, build_number, filename, sha256.lower()


def download_latest_paper(server_jar: Path, *, overwrite: bool = False) -> tuple[Path, str | None, str, int]:
    """Report current version and download latest stable Paper build to ``server_jar``.

    Existing server files are never replaced unless ``overwrite=True``. The download
    is checked against Paper's published SHA-256 before being atomically installed.
    """
    destination = server_jar.expanduser().resolve()
    current_version = detect_paper_version(destination)
    latest_version, build_number, filename, expected_hash = get_latest_paper_build()

    if destination.exists() and not overwrite:
        raise PluginInstallError(
            f"Server file already exists ({current_version or 'version unknown'}). "
            f"Latest Paper is Minecraft {latest_version}, build {build_number}. "
            "Choose a new --server-jar path or pass --overwrite to replace it."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    url = (
        f"{PAPER_API}/projects/paper/versions/{latest_version}/builds/{build_number}"
        f"/downloads/{filename}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    temp_path: Path | None = None
    digest = hashlib.sha256()
    total = 0
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.", suffix=".download", dir=destination.parent, delete=False
        ) as output:
            temp_path = Path(output.name)
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise PluginInstallError("Paper server download exceeds the 250 MB safety limit.")
                    digest.update(chunk)
                    output.write(chunk)
            output.flush()

        if digest.hexdigest() != expected_hash:
            raise PluginInstallError("Paper server JAR checksum mismatch; refusing to install it.")
        try:
            with zipfile.ZipFile(temp_path) as archive:
                if archive.testzip() is not None:
                    raise PluginInstallError("Downloaded Paper JAR failed ZIP integrity validation.")
        except (OSError, zipfile.BadZipFile) as exc:
            raise PluginInstallError(f"Downloaded Paper file is not a valid JAR: {exc}") from exc

        if overwrite:
            # Keep the existing server binary untouched until the verified new file is ready.
            backup_path = destination.with_name(destination.name + ".previous")
            if backup_path.exists():
                raise PluginInstallError(
                    f"Backup already exists at {backup_path}; move it before updating."
                )
            if destination.exists():
                shutil.copy2(destination, backup_path)
            temp_path.replace(destination)
        else:
            # Atomic create without clobbering a file created concurrently.
            temp_path.hardlink_to(destination)
            temp_path.unlink()
        return destination, current_version, latest_version, build_number
    except PluginInstallError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PluginInstallError(f"Could not download latest Paper server: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
