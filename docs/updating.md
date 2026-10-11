# Updating & Uninstalling

These scripts apply to the [barebones (non-Docker) install](installation.md#barebones-no-docker).
For Docker, pull the new image/tag and `docker compose up -d --build` (or
`docker compose -f docker-compose.prod.yml up -d` for tagged images)
instead.

## Updating

Run the standalone update script to pull the latest code, rebuild, and
restart the services — no interactive prompts, preserves your
configuration:

```bash
bash ~/hdhr-open/deploy/update.sh
```

Or as a one-liner without a local checkout:

```bash
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/update.sh | bash
```

Rerunning the main installer also works and has the same effect — see
[Installation](installation.md#barebones-no-docker).

## Uninstalling

Run the standalone uninstall script to stop and disable the systemd
services, remove the sudoers rule, and delete the installation directory:

```bash
bash ~/hdhr-open/deploy/uninstall.sh
```

Or as a one-liner without a local checkout:

```bash
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/uninstall.sh | bash
```

Or via the installer flag:

```bash
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/install.sh | bash -s -- --uninstall
```

### Uninstallation options

- `--keep-data`: Removes systemd services and the sudoers entry, but
  preserves your database, `.env` files, and the rest of `~/hdhr-open`:
  ```bash
  bash ~/hdhr-open/deploy/uninstall.sh --keep-data
  ```
- `-y, --yes, --force`: Non-interactive mode (skips confirmation prompts):
  ```bash
  bash ~/hdhr-open/deploy/uninstall.sh -y
  ```
