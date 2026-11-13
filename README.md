# pluGET-mejorado

A small tool for safely installing Minecraft plugins and updating a Paper server. Plugins downloaded from marketplaces must be obtained through the provider's official flow; public Spigot resources can also be installed using Spiget.

## Check and download the latest Paper server

Install/download the stable Paper server build to a new path (the folder is created if needed):

```bash
python pluget_paid.py --paper-latest --server-jar /path/to/server/paper.jar
```

The tool checks the existing JAR's embedded version when it can, queries Paper's public API for the latest stable Minecraft version and build, downloads the official JAR, verifies its SHA-256 checksum, and validates its ZIP/JAR structure. If a server JAR already exists, it will not replace it unless you explicitly add `--overwrite`; when replacing, it saves the old file as `paper.jar.previous`. Stop the Minecraft server before replacing its server JAR.

This feature currently supports **Paper only**. It does not update Spigot, Purpur, Fabric, Forge, or Vanilla server files. Some server JARs do not expose a readable embedded version, in which case the current version is reported as unknown. ClamAV is not used for server JARs because Paper's published SHA-256 checksum is verified; keep your software and server backups current.

## Install a plugin you own

Install ClamAV and ensure the `clamscan` command is available on `PATH`. Keep its virus definitions updated. Then:

```bash
python pluget_paid.py /path/to/YourPlugin.jar --plugins-dir /path/to/server/plugins
```

The installer checks that the file is a JAR containing `plugin.yml` or `paper-plugin.yml`, scans it with ClamAV, and only then copies it into the target directory. It fails closed if ClamAV is unavailable, the scan detects malware, or the scanner errors or times out. It does not replace an existing file unless `--overwrite` is supplied. Stop the Minecraft server before installing or replacing plugins.

## Spigot resources

Publicly downloadable Spigot resources can be installed by their numeric resource ID using Spiget's public API. For example:

```bash
python pluget_paid.py --spigot 28140 --plugins-dir /path/to/server/plugins
```

The downloaded plugin JAR is validated and scanned with ClamAV. This integration does not sign in to a Spigot account, download paid/premium resources, or bypass purchase controls. Download purchased resources through Spigot's supported account flow, then install the local JAR.

A clean antivirus result is not a guarantee that a plugin is safe. ClamAV signatures can miss new or obfuscated threats; use trusted sources and keep definitions up to date.

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests require no network access; external API and scanner calls are mocked.

## Scope

This is an initial implementation, not a complete copy of upstream [Neocky/pluGET](https://github.com/Neocky/pluGET). Paper server updates and public Spigot/Spiget resource installs are supported. Remote SFTP/FTP uploads and provider-specific official login flows are not implemented yet.
