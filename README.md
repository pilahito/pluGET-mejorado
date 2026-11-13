# pluGET-mejorado

A small tool for safely installing Minecraft plugins and updating a Paper server. Public Spigot resources can be downloaded via Spiget, with a compatibility check against the server's Minecraft version.

## Install a Spigot plugin compatible with your server

If you have a Paper server JAR, provide its path and the tool will try to read its Minecraft version:

```bash
python pluget_paid.py --spigot 28140 --paper-server-jar /path/to/server/paper.jar --plugins-dir /path/to/server/plugins
```

Or provide the server's Minecraft version directly (also works with Spigot and other Bukkit-compatible servers):

```bash
python pluget_paid.py --spigot 28140 --minecraft-version 1.21.4 --plugins-dir /path/to/server/plugins
```

Before downloading, the program compares the requested version with Spiget's `testedVersions` metadata. It refuses to download when the version is not listed or the metadata is missing. This check is only as accurate as the resource's metadata and cannot guarantee runtime compatibility. Many Spigot server JARs do not expose their Minecraft version in a standard way; in that case, specify `--minecraft-version` yourself.

Spiget only provides a resource's currently downloadable version, not necessarily every historical release by Minecraft version. This integration does not sign in to a Spigot account, download paid/premium resources, or bypass purchase controls. For purchased resources, download through Spigot's supported account flow and install the local JAR as described below.

## Install a plugin you own

Install ClamAV and ensure the `clamscan` command is available on `PATH`. Keep its virus definitions updated. Then:

```bash
python pluget_paid.py /path/to/YourPlugin.jar --plugins-dir /path/to/server/plugins
```

The installer checks that the file is a JAR containing `plugin.yml` or `paper-plugin.yml`, scans it with ClamAV, and only then copies it into the target directory. It does not replace an existing file unless `--overwrite` is supplied. Stop the Minecraft server before installing or replacing plugins.

## Check and download the latest Paper server

```bash
python pluget_paid.py --paper-latest --server-jar /path/to/server/paper.jar
```

The tool detects the current version when possible, downloads the latest stable Paper build, checks its published SHA-256, and preserves an existing server JAR as `.previous` when `--overwrite` is used. Stop the server before updating. This currently supports Paper only.

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests require no network access; external API and scanner calls are mocked.

## Security notes

A clean ClamAV result does not guarantee a plugin is safe. Use trusted sources and keep antivirus definitions updated. Server JAR integrity is checked with Paper's published SHA-256 checksum.
