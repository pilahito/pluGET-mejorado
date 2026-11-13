# pluGET-mejorado

A small, safe first step toward managing plugins obtained from different Minecraft plugin providers. This repository provides a local installer for plugin JARs that you have already downloaded through the provider's official purchase/account flow.

## Install a plugin you own

Install ClamAV and ensure the `clamscan` command is available on `PATH`. Keep its virus definitions updated. Then:

```bash
python -m pip install .
pluget-paid /path/to/YourPlugin.jar --plugins-dir /path/to/server/plugins
```

Or run without installing:

```bash
python pluget_paid.py /path/to/YourPlugin.jar --plugins-dir /path/to/server/plugins
```

The installer checks that the file is a JAR containing `plugin.yml` or `paper-plugin.yml`, scans it with ClamAV, and only then copies it into the target directory. It fails closed if ClamAV is unavailable, the scan detects malware, or the scanner errors or times out. It does not replace an existing file unless `--overwrite` is supplied. Stop the Minecraft server before installing or replacing plugins.

A clean antivirus result is not a guarantee that a plugin is safe. ClamAV signatures can miss new or obfuscated threats; obtain plugins from trusted sources, keep definitions current, and review permissions and plugin behavior. This tool does not execute or load the JAR while scanning.

## Marketplace logins and paid downloads

There is no universal login that works across SpigotMC, BuiltByBit, Polymart, and other providers. This tool does not store passwords, scrape websites, bypass purchase checks, or automate downloads around a provider's restrictions. Provider-specific authentication/download integrations should only be added when that provider offers an official API or supported authorization flow. Until then, download the plugin while signed in through the provider and install the JAR locally as shown above.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Scope

This is an initial implementation, not a complete copy of upstream [Neocky/pluGET](https://github.com/Neocky/pluGET). Existing upstream integrations include Spigot/Spiget, Modrinth, and GitHub; this starter adds a local install path for legitimately obtained plugin files. Remote SFTP/FTP uploads and provider-specific official login flows are not implemented yet.
