"""Install a locally downloaded Minecraft plugin JAR into a server's plugins folder."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


class PluginInstallError(Exception):
    """Raised when a plugin cannot be safely installed."""


def validate_plugin_jar(jar_path: Path) -> None:
    """Check that ``jar_path`` is a readable JAR with a Bukkit/Paper descriptor."""
    if not jar_path.is_file():
        raise PluginInstallError(f"Not a regular file: {jar_path}")
    if jar_path.suffix.lower() != ".jar":
        raise PluginInstallError("The source file must have a .jar extension.")
    try:
        with zipfile.ZipFile(jar_path) as archive:
            entries = set(archive.namelist())
            descriptor = next(
                (name for name in ("plugin.yml", "paper-plugin.yml") if name in entries),
                None,
            )
            if descriptor is None:
                raise PluginInstallError(
                    "This JAR does not contain plugin.yml or paper-plugin.yml."
                )
            info = archive.getinfo(descriptor)
            if info.file_size > 1024 * 1024:
                raise PluginInstallError("The plugin descriptor is unexpectedly large.")
            if not archive.read(descriptor).strip():
                raise PluginInstallError("The plugin descriptor is empty.")
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise PluginInstallError(f"Could not read a valid plugin JAR: {exc}") from exc


def scan_for_malware(jar_path: Path, *, timeout: int = 120) -> None:
    """Scan a JAR with ClamAV's ``clamscan`` and fail closed on errors."""
    scanner = shutil.which("clamscan")
    if scanner is None:
        raise PluginInstallError(
            "Malware scan unavailable: install ClamAV and make 'clamscan' available "
            "on PATH. The plugin was not installed."
        )
    try:
        result = subprocess.run(
            [scanner, "--no-summary", "--", str(jar_path)],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PluginInstallError(
            f"Malware scan timed out after {timeout} seconds; plugin was not installed."
        ) from exc
    except OSError as exc:
        raise PluginInstallError(f"Could not run ClamAV: {exc}") from exc
    if result.returncode == 0:
        return
    if result.returncode == 1:
        detail = (result.stdout or result.stderr).strip().splitlines()
        finding = detail[-1] if detail else "ClamAV reported an infection."
        raise PluginInstallError(f"Malware detected; plugin was not installed: {finding}")
    detail = (result.stderr or result.stdout).strip()
    if len(detail) > 500:
        detail = detail[-500:]
    raise PluginInstallError(
        f"ClamAV scan failed (exit code {result.returncode}); plugin was not installed. {detail}"
    )


def install_plugin(jar_path: Path, plugin_dir: Path, *, overwrite: bool = False) -> Path:
    """Scan, validate, and atomically copy a plugin JAR into ``plugin_dir``."""
    source = jar_path.expanduser().resolve()
    destination_dir = plugin_dir.expanduser().resolve()
    validate_plugin_jar(source)
    scan_for_malware(source)
    if source == destination_dir / source.name:
        raise PluginInstallError("The JAR is already in the target plugins directory.")
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        if not destination_dir.is_dir():
            raise PluginInstallError(f"Plugin destination is not a directory: {destination_dir}")
    except OSError as exc:
        raise PluginInstallError(f"Could not prepare plugin directory: {exc}") from exc
    destination = destination_dir / source.name
    if destination.exists() and not overwrite:
        raise PluginInstallError(
            f"{destination.name} already exists; pass --overwrite to replace it."
        )
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{source.name}.", suffix=".tmp", dir=destination_dir, delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)
            with source.open("rb") as source_file:
                shutil.copyfileobj(source_file, temp_file)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        if overwrite:
            os.replace(temp_path, destination)
        else:
            os.link(temp_path, destination)
            temp_path.unlink()
        return destination
    except FileExistsError as exc:
        raise PluginInstallError(
            f"{destination.name} already exists; pass --overwrite to replace it."
        ) from exc
    except OSError as exc:
        raise PluginInstallError(f"Could not install plugin: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install plugins, update Spigot resources, or manage Paper server builds."
    )
    parser.add_argument("jar", nargs="?", type=Path, help="Path to your downloaded plugin .jar")
    parser.add_argument("--spigot", metavar="RESOURCE_ID", help="Download a public Spigot resource via Spiget")
    parser.add_argument("--update-spigot", type=Path, metavar="CONFIG.json", help="Update configured Spigot resources")
    parser.add_argument("--minecraft-version", metavar="VERSION", help="Minecraft version for Spiget compatibility checks")
    parser.add_argument("--paper-server-jar", type=Path, help="Paper JAR used to detect Minecraft version")
    parser.add_argument("--paper-latest", action="store_true", help="Download the latest stable Paper server")
    parser.add_argument("--server-jar", type=Path, help="Paper server JAR path")
    parser.add_argument("--plugins-dir", type=Path, help="Server plugins directory")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing plugin/server JAR")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    modes = sum((args.jar is not None, args.spigot is not None, args.update_spigot is not None, args.paper_latest))
    if modes != 1:
        parser.error("choose exactly one mode: local JAR, --spigot ID, --update-spigot CONFIG.json, or --paper-latest")

    try:
        if args.update_spigot is not None:
            if args.minecraft_version or args.paper_server_jar or args.plugins_dir:
                parser.error("--update-spigot reads version and plugins directory from its JSON config")
            from spigot_updates import update_configured_spigot
            results = update_configured_spigot(args.update_spigot)
            failed = False
            for resource_id, status, path in results:
                print(f"Spigot {resource_id}: {status}" + (f" -> {path}" if path else ""))
                failed |= status.startswith("error:")
            return 1 if failed else 0
        if args.paper_latest:
            if args.server_jar is None:
                parser.error("--paper-latest requires --server-jar PATH")
            from paper_server import download_latest_paper
            installed, current, latest, build = download_latest_paper(args.server_jar, overwrite=args.overwrite)
            print(f"Current Paper/Minecraft version: {current or 'could not be detected'}")
            print(f"Latest stable Paper build: Minecraft {latest}, build {build}")
            print(f"Downloaded server JAR: {installed}")
        elif args.spigot:
            if args.plugins_dir is None:
                parser.error("--spigot requires --plugins-dir PATH")
            from spigot import install_spigot_resource
            installed = install_spigot_resource(
                args.spigot, args.plugins_dir,
                minecraft_version=args.minecraft_version,
                server_jar=args.paper_server_jar,
                overwrite=args.overwrite,
            )
            print(f"Installed plugin: {installed}")
        else:
            if args.plugins_dir is None:
                parser.error("a local plugin JAR requires --plugins-dir PATH")
            if args.minecraft_version or args.paper_server_jar:
                parser.error("version options are only available with --spigot")
            installed = install_plugin(args.jar, args.plugins_dir, overwrite=args.overwrite)
            print(f"Installed plugin: {installed}")
    except PluginInstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
