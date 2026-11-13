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
    _latest_version_name,
    _safe_filename,
    is_prerelease_version,
    _is_supported_version,
    _normalize_version,
)


def _validate_jar_name(name: str) -> str:
    """Accept only a bare .jar file name, never a path."""
    if not isinstance(name, str) or not name.endswith(".jar") or name != Path(name).name or name in {".jar", "..jar"}:
        raise PluginInstallError(f"'archivo' must be a bare .jar file name, got: {name!r}")
    return name


def update_spigot_resource(
    resource_id: str,
    plugins_dir: Path,
    minecraft_version: str,
    *,
    stage_dir: Path | None = None,
    filename: str | None = None,
    stable_only: bool = False,
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

    if stable_only:
        version_name = _latest_version_name(resource_id)
        if is_prerelease_version(version_name):
            return f"skipped: latest version '{version_name}' is a prerelease", None

    destination_dir = plugins_dir.expanduser().resolve()
    # Use the name of the JAR already installed when given, so an update replaces it
    # instead of leaving two copies of the same plugin in the folder.
    name = _validate_jar_name(filename) if filename else _safe_filename(resource["name"], resource_id)
    destination = destination_dir / name
    target_dir = stage_dir.expanduser().resolve() if stage_dir is not None else destination_dir
    with tempfile.TemporaryDirectory(prefix="pluget-spigot-update-") as temp_dir:
        candidate = Path(temp_dir) / destination.name
        _download_resource(resource_id, candidate)
        candidate_hash = hashlib.sha256(candidate.read_bytes()).digest()
        if destination.is_file():
            existing_hash = hashlib.sha256(destination.read_bytes()).digest()
            if candidate_hash == existing_hash:
                return "unchanged", destination
        installed = install_plugin(candidate, target_dir, overwrite=True)
        return ("staged" if stage_dir is not None else "updated"), installed


def update_configured_spigot(
    config_path: Path, *, stage_dir: Path | None = None
) -> list[tuple[str, str, Path | None]]:
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

    stable_only = bool(config.get("solo_estables", False))
    results: list[tuple[str, str, Path | None]] = []
    for entry in resources:
        # A resource is either an ID, or {"id": 9089, "archivo": "InstalledName.jar"}.
        if isinstance(entry, dict):
            resource_id, filename = entry.get("id"), entry.get("archivo")
        else:
            resource_id, filename = entry, None
        try:
            status, path = update_spigot_resource(
                str(resource_id), Path(plugins_dir), minecraft_version.strip(),
                stage_dir=stage_dir, filename=filename, stable_only=stable_only,
            )
            results.append((str(resource_id), status, path))
        except PluginInstallError as exc:
            results.append((str(resource_id), f"error: {exc}", None))
    return results
