# pluGET-mejorado

A small, safe first step toward managing plugins obtained from different Minecraft plugin providers. This repository provides a local installer for plugin JARs that you have already downloaded through the provider's official purchase/account flow, plus installation of publicly downloadable Spigot resources through Spiget.

## Install a plugin you own

Install ClamAV and ensure the `clamscan` command is available on `PATH`. Keep its virus definitions updated. Then:

```bash
python pluget_paid.py /path/to/YourPlugin.jar --plugins-dir /path/to/server/plugins
```

The installer checks that the file is a JAR containing `plugin.yml` or `paper-plugin.yml`, scans it with ClamAV, and only then copies it into the target directory. It fails closed if ClamAV is unavailable, the scan detects malware, or the scanner errors or times out. It does not replace an existing file unless `--overwrite` is supplied. Stop the Minecraft server before installing or replacing plugins.

## Spigot resources

Publicly downloadable Spigot resources can be installed by their numeric resource ID using Spiget's public API. For example, the LuckPerms Spigot resource ID is `28140`:

```bash
python pluget_paid.py --spigot 28140 --plugins-dir /path/to/server/plugins
```

The downloaded JAR is validated and scanned by ClamAV before installation. This integration does not sign in to a Spigot account, download paid/premium resources, or bypass purchase or download controls. For a purchased resource, download it through Spigot's supported account flow and install the local JAR with the first command. The code uses Spiget's public API; availability and API limits are controlled by that service.

A clean antivirus result is not a guarantee that a plugin is safe. ClamAV signatures can miss new or obfuscated threats; obtain plugins from trusted sources, keep definitions current, and review permissions and plugin behavior. This tool does not execute or load the JAR while scanning.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Scope

This is an initial implementation, not a complete copy of upstream [Neocky/pluGET](https://github.com/Neocky/pluGET). Remote SFTP/FTP uploads and provider-specific official login flows are not implemented yet.
