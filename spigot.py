"""Install public, downloadable Spigot resources via the Spiget API."""

from __future__ import annotations

import json
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from paper_server import detect_paper_version
from pluget_paid import PluginInstallError, install_plugin

SPIGET_API = "https://api.spiget.org/v2"
USER_AGENT = "pluGET-mejorado/0.1 (Spigot resource installer)"
REQUEST_TIMEOUT = 30
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


def _request(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT)


def _fetch_resource(resource_id: str) -> dict[str, Any]:
    url = f"{SPIGET_API}/resources/{resource_id}"
    try:
        with _request(url) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise PluginInstallError(
            f"Spiget could not retrieve resource {resource_id} (HTTP {exc.code}). "
            "It may not exist or may not be publicly downloadable."
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginInstallError(f"Could not connect to Spiget: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        raise PluginInstallError("Spiget returned invalid resource information.")
    return data


def _normalize_version(version: str) -> str:
    """Normalize common Minecraft version prefixes without guessing compatibility."""
    normalized = version.strip()
    if normalized.lower().startswith("minecraft "):
        normalized = normalized[len("minecraft "):].strip()
    if normalized.lower().startswith("mc "):
        normalized = normalized[3:].strip()
    return normalized


def _is_supported_version(server_version: str, tested_versions: list[Any]) -> bool:
    """Match exact versions or explicit major/minor entries (e.g. 1.20 covers 1.20.4)."""
    target = _normalize_version(server_version)
    for value in tested_versions:
        if not isinstance(value, str):
            continue
        tested = _normalize_version(value)
        if target == tested:
            return True
        if re.fullmatch(r"\d+\.\d+", tested) and target.startswith(tested + "."):
            return True
    return False


_PRERELEASE_MARKERS = re.compile(
    r"(?i)(?<![a-z])(alpha|beta|snapshot|nightly|dev|pre|prerelease|pre-release|rc)(?![a-z])\d*"
)


def is_prerelease_version(version_name: str) -> bool:
    """True when a version name carries a prerelease marker (beta, SNAPSHOT, RC, dev...).

    It only sees what is written in the version name, not hidden prerelease status.
    """
    return bool(_PRERELEASE_MARKERS.search(version_name or ""))


def _latest_version_name(resource_id: str) -> str:
    """Name of the latest published version of a resource, from Spiget."""
    url = f"{SPIGET_API}/resources/{resource_id}/versions/latest"
    try:
        with _request(url) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginInstallError(f"Could not read the latest version of resource {resource_id}: {exc}") from exc
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str):
        raise PluginInstallError(f"Spiget returned no version name for resource {resource_id}.")
    return name


def _safe_filename(resource_name: str, resource_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", resource_name).strip(".-_")
    if not cleaned:
        cleaned = f"spigot-plugin-{resource_id}"
    return f"{cleaned[:100]}-spigot-{resource_id}.jar"


def _download_resource(resource_id: str, destination: Path) -> None:
    url = f"{SPIGET_API}/resources/{resource_id}/download"
    try:
        with _request(url) as response, destination.open("wb") as output:
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise PluginInstallError(
                        f"Download exceeds the {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB safety limit."
                    )
                output.write(chunk)
    except PluginInstallError:
        destination.unlink(missing_ok=True)
        raise
    except urllib.error.HTTPError as exc:
        destination.unlink(missing_ok=True)
        raise PluginInstallError(
            f"Spiget download failed (HTTP {exc.code}). The resource may require purchase "
            "or may not permit API downloads."
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise PluginInstallError(f"Could not download Spigot resource: {exc}") from exc


def install_spigot_resource(
    resource_id: str,
    plugins_dir: Path,
    *,
    minecraft_version: str | None = None,
    server_jar: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Download, check Spiget's tested-version metadata, scan, and install a public plugin.

    Supply the Minecraft version explicitly, or provide a Paper server JAR whose
    embedded version can be detected. Spiget's testedVersions metadata is advisory
    and may be incomplete; this check cannot guarantee runtime compatibility.
    """
    resource_id = str(resource_id)
    if not resource_id.isdecimal():
        raise PluginInstallError("Spigot resource ID must contain only digits.")

    if minecraft_version and server_jar:
        raise PluginInstallError("Use either --minecraft-version or --server-jar, not both.")
    if server_jar is not None:
        minecraft_version = detect_paper_version(server_jar.expanduser())
        if minecraft_version is None:
            raise PluginInstallError(
                f"Could not detect the Minecraft version from {server_jar}. "
                "Specify --minecraft-version explicitly."
            )
    if not minecraft_version:
        raise PluginInstallError(
            "Minecraft version is required. Pass --minecraft-version X.Y[.Z] or "
            "--server-jar PATH (automatic detection currently supports Paper JARs)."
        )
    minecraft_version = _normalize_version(minecraft_version)
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", minecraft_version):
        raise PluginInstallError("Minecraft version must look like 1.21 or 1.21.4.")

    resource = _fetch_resource(resource_id)
    tested_versions = resource.get("testedVersions")
    if not isinstance(tested_versions, list) or not tested_versions:
        raise PluginInstallError(
            f"Spiget does not provide tested Minecraft versions for '{resource['name']}'; "
            "compatibility cannot be checked, so the download was not installed."
        )
    if not _is_supported_version(minecraft_version, tested_versions):
        supported = ", ".join(str(v) for v in tested_versions if isinstance(v, str)) or "not listed"
        raise PluginInstallError(
            f"'{resource['name']}' is not marked as tested for Minecraft {minecraft_version}. "
            f"Spiget lists: {supported}. The download was not installed."
        )

    filename = _safe_filename(resource["name"], resource_id)
    with tempfile.TemporaryDirectory(prefix="pluget-spigot-") as temp_dir:
        jar_path = Path(temp_dir) / filename
        _download_resource(resource_id, jar_path)
        return install_plugin(jar_path, plugins_dir, overwrite=overwrite)
