"""Update configured, publicly downloadable Spigot resources via Spiget."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from pluget_paid import PluginInstallError, install_plugin
from spigot import (
    MAX_DOWNLOAD_BYTES,
    _download_resource,
    _fetch_resource,
    _safe_filename,
    _is_supported_version,
    _normalize_version,
)


def update_spigot_resource(
    resource_id: str,
    plugins_dir: Path,
    minecraft_version: str,
) -> tuple[str, Path | None]:
    """Install a compatible public Spiget resource only when its JAR has changed.

    Returns ``("updated", path)`` or ``("unchanged", path)``. Compatibility
    is based on Spiget's `testedVersions` metadata and cannot guarantee runtime
    support. Antivirus scanning and safe replacement are performed by install_plugin.
    """
    resource_id = str(resource_id)
    if not resource_id.isdecimal():
        raise PluginInstallError("Spigot resource ID must contain only digits.")
    if not minecraft_version:
        raise PluginInstallError("Minecraft version is required for Spigot updates.")

    normalized_version = _normalize_version(minecraft_version)
    resource = _fetch_resource(resource_id)
    tested_versions: Any = resource.get("testedVersions")
    if not isinstance(tested_versions, list) or not tested_versions:
        raise PluginInstallError(
            f"Spiget does not provide tested Minecraft versions for '{resource['name']}'; "
            "update skipped because compatibility cannot be checked."
        )
    if not _is_supported_version(normalized_version, tested_versions):
        raise PluginInstallError(
            f"'{resource['name']}' is not marked as tested for Minecraft {normalized_version}; "
            "update skipped."
        )

    destination_dir = plugins_dir.expanduser().resolve()
    destination = destination_dir / _safe_filename(resource["name"], resource_id)
    with tempfile.TemporaryDirectory(prefix="pluget-spigot-update-") as temp_dir:
        candidate = Path(temp_dir) / destination.name
        _download_resource(resource_id, candidate)
        candidate_hash = hashlib.sha256(candidate.read_bytes()).digest()
        if destination.is_file():
            existing_hash = hashlib.sha256(destination.read_bytes()).digest()
            if candidate_hash == existing_hash:
                return "unchanged", destination
        installed = install_plugin(candidate, destination_dir, overwrite=True)
        return "updated", installed


def update_configured_spigot(config_path: Path) -> list[tuple[str, str, Path | None]]:
    """Update the public Spigot resources listed in a JSON config file."""
    config_path = config_path.expanduser()
    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginInstallError(f"Could not read update config {config_path}: {exc}") from exc

    if not isinstance(config, dict):
        raise PluginInstallError("Update config must be a JSON object.")
    minecraft_version = config.get("minecraft_version")
    plugins_dir = config.get("plugins_dir")
    resources = config.get("resources")
    if not isinstance(minecraft_version, str) or not minecraft_version.strip():
        raise PluginInstallError("Update config needs a non-empty 'minecraft_version'.")
    if not isinstance(plugins_dir, str) or not plugins_dir.strip():
        raise PluginInstallError("Update config needs a non-empty 'plugins_dir'.")
    if not isinstance(resources, list) or not resources:
        raise PluginInstallError("Update config needs a non-empty 'resources' list of Spigot IDs.")

    results: list[tuple[str, str, Path | None]] = []
    for resource_id in resources:
        try:
            status, path = update_spigot_resource(
                str(resource_id), Path(plugins_dir), minecraft_version.strip()
            )
            results.append((str(resource_id), status, path))
        except PluginInstallError as exc:
            results.append((str(resource_id), f"error: {exc}", None))
    return results
