"""Install public, downloadable Spigot resources via the Spiget API."""

from __future__ import annotations

import json
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

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
    resource_id: str, plugins_dir: Path, *, overwrite: bool = False
) -> Path:
    """Download a publicly accessible resource through Spiget, scan, and install it.

    This integration uses Spiget's public API and does not authenticate to SpigotMC,
    access paid resources, or bypass a provider's purchase or download controls.
    """
    resource_id = str(resource_id)
    if not resource_id.isdecimal():
        raise PluginInstallError("Spigot resource ID must contain only digits.")

    resource = _fetch_resource(resource_id)
    filename = _safe_filename(resource["name"], resource_id)
    with tempfile.TemporaryDirectory(prefix="pluget-spigot-") as temp_dir:
        jar_path = Path(temp_dir) / filename
        _download_resource(resource_id, jar_path)
        return install_plugin(jar_path, plugins_dir, overwrite=overwrite)
