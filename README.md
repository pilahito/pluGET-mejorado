# pluGET-mejorado

A small tool for safely installing Minecraft plugins and updating a Paper server. Public Spigot resources can be downloaded via Spiget, with compatibility checked against your Minecraft version.

## Automatic Spigot updates on Ubuntu

Create a JSON file such as `spigot-updates.json` (use absolute paths):

```json
{
  "minecraft_version": "1.21.4",
  "plugins_dir": "/home/minecraft/server/plugins",
  "resources": [28140, 12345]
}
```

Install ClamAV and update its signatures before enabling automatic installation. Run one update pass manually first:

```bash
sudo apt update && sudo apt install clamav clamav-freshclam
sudo freshclam
python3 pluget_paid.py --update-spigot /home/minecraft/spigot-updates.json
```

The updater checks Spiget's `testedVersions` metadata for each resource, downloads only public Spigot resources, compares each JAR with the installed file, and skips unchanged files. Changed JARs are validated and scanned with ClamAV before atomic replacement. If an update fails compatibility checks, network access, validation, or scanning, the existing plugin remains in place. Stop the Minecraft server before updates; schedule a maintenance window so the server is not loading a JAR while it is replaced.

Spiget provides the current publicly downloadable resource version; it may not expose older files individually by Minecraft version. Compatibility relies on author-provided metadata and is not guaranteed. Paid resources are not authenticated or downloaded by this command. Obtain purchased plugins through Spigot's supported account flow; additional marketplaces can be integrated later through their official interfaces.

### Prepare updates without write access to the server folder (staging)

If the plugins folder belongs to another Linux user, prepare the updates in a staging folder you own and let that user copy them in:

```bash
python3 pluget_paid.py --update-spigot /home/minecraft/spigot-updates.json --stage-dir /home/minecraft/staging
```

Each staged JAR is validated and scanned with ClamAV, and gets a `<name>.jar.informe.json` with its Spigot ID, size and SHA-256. Nothing is written to the plugins folder. Applying the files, and restarting the server, stays a manual step.

Two optional settings in the JSON config:

```json
{
  "minecraft_version": "1.21.4",
  "plugins_dir": "/home/minecraft/server/plugins",
  "solo_estables": true,
  "resources": [28140, {"id": 9089, "archivo": "EssentialsX-2.22.1.jar"}]
}
```

- `archivo` is the file name of the JAR already installed. Without it the updater saves `Name-spigot-ID.jar`, which would sit next to the existing JAR and load the plugin twice. Use `archivo` for every plugin that is already installed.
- `solo_estables` skips a resource when its latest version name has a prerelease marker such as beta, alpha, RC, SNAPSHOT or dev. It only sees what is written in the version name.

### Schedule daily with Ubuntu cron

Run `crontab -e` as the same Linux user that owns the Minecraft server and add a daily job (adjust paths and time):

```cron
0 5 * * * /usr/bin/python3 /home/minecraft/pluGET-mejorado/pluget_paid.py --update-spigot /home/minecraft/spigot-updates.json >> /home/minecraft/spigot-updates.log 2>&1
```

Cron does not stop the Minecraft server. For production, schedule this during a maintenance window or stop/start the service around the update using a dedicated service manager and carefully reviewed permissions.

## Install an individual public Spigot resource

```bash
python3 pluget_paid.py --spigot 28140 --minecraft-version 1.21.4 --plugins-dir /home/minecraft/server/plugins
```

A Paper JAR can be used to detect its Minecraft version:

```bash
python3 pluget_paid.py --spigot 28140 --paper-server-jar /home/minecraft/server/paper.jar --plugins-dir /home/minecraft/server/plugins
```

## Install a plugin JAR you already downloaded

```bash
python3 pluget_paid.py /path/to/YourPlugin.jar --plugins-dir /home/minecraft/server/plugins
```

This path requires ClamAV, validates the plugin JAR, and does not replace an existing file without `--overwrite`.

## Update Paper server

```bash
python3 pluget_paid.py --paper-latest --server-jar /home/minecraft/server/paper.jar
```

The tool verifies Paper's published SHA-256 checksum. Existing server JARs are preserved unless you explicitly add `--overwrite`; stop the server before replacing one.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Tests mock network and scanner calls. A clean antivirus result does not guarantee a plugin is safe. Use trusted sources and keep ClamAV definitions current.
