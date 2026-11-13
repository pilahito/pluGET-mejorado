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
    """Scan a JAR with ClamAV's ``clamscan`` and fail closed on errors.

    ClamAV must be installed and its virus definitions kept up to date. A clean
    result is not a guarantee of safety; this is one defense-in-depth check and
    does not execute or load the plugin.
    """
    scanner = shutil.which("clamscan")
    if scanner is None:
        raise PluginInstallError(
            "Malware scan unavailable: install ClamAV and make 'clamscan' available "
            "on PATH. The plugin was not installed."
        )

    try:
        result = subprocess.run(
            [scanner, "--no-summary", "--", str(jar_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
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
        f"ClamAV scan failed (exit code {result.returncode}); plugin was not installed. "
        f"{detail}"
    )


def install_plugin(jar_path: Path, plugin_dir: Path, *, overwrite: bool = False) -> Path:
    """Scan, validate, and atomically copy a plugin JAR into ``plugin_dir``.

    This function only installs a local file supplied by the user. It does not log in
    to a marketplace or download content, and it never handles provider credentials.
    """
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
            # Hard-linking gives no-overwrite installs an atomic, race-safe create.
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
        description="Scan and install a plugin JAR obtained from its official provider."
    )
    parser.add_argument("jar", nargs="?", type=Path, help="Path to your downloaded plugin .jar")
    parser.add_argument(
        "--spigot", metavar="RESOURCE_ID",
        help="Download a publicly accessible Spigot resource by its numeric ID via Spiget",
    )
    parser.add_argument(
        "--plugins-dir", required=True, type=Path,
        help="Server plugins directory (created if it does not exist)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace a plugin JAR with the same filename",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.jar) == bool(args.spigot):
        parser.error("provide exactly one source: a local JAR path or --spigot RESOURCE_ID")

    try:
        if args.spigot:
            from spigot import install_spigot_resource

            installed = install_spigot_resource(
                args.spigot, args.plugins_dir, overwrite=args.overwrite
            )
        else:
            installed = install_plugin(args.jar, args.plugins_dir, overwrite=args.overwrite)
    except PluginInstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Installed plugin: {installed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
