# Proxmox Guest Updates for Home Assistant

Shows OS and app updates for your Proxmox LXCs and VMs as Home Assistant **update** entities, and installs them when you press **Install**. Nothing updates on its own.

Works together with [pveupdate](https://github.com/Niiikoc/Pveupdate), which runs on the Proxmox host and does the actual work: snapshot first, then OS packages (`apt`/`apk`), then the app's own update (community-scripts `update` or your own command).

It sits next to the regular Proxmox VE integrations; it doesn't replace them. The Proxmox API can't run commands inside containers, which is why pveupdate is needed on the host.

## What you get

- **One update entity per tracked guest**, e.g. *zigbee2mqtt: 2.9.1 → 2.14.2 + 2 packages*, listed under Settings → Updates with release notes (the package list) and an Install button with progress.
- **Proxmox host device** with:
  - *Check for updates* and *Update all pending* buttons
  - *Guests with updates* sensor (for automations and notifications)
  - *Last check* and *Activity* (idle / checking / updating) sensors
- Automatic read-only checks every 6 hours (configurable, or off).

## Setup

### 1. On the Proxmox host

```bash
base=https://raw.githubusercontent.com/Niiikoc/Pveupdate/main
curl -fsSL $base/pveupdate.py -o /usr/local/bin/pveupdate && chmod +x /usr/local/bin/pveupdate
pveupdate track                      # choose the guests to manage

curl -fsSL $base/systemd/pveupdate-serve.service -o /etc/systemd/system/pveupdate-serve.service
systemctl daemon-reload && systemctl enable --now pveupdate-serve
pveupdate token                      # copy this for step 3
```

The API listens on port 8765 and requires the token for every request. It only accepts these actions: read status, start a check, and update tracked guests.

### 2. Install the integration

HACS → ⋮ → **Custom repositories** → add `https://github.com/Niiikoc/ha-pveupdate` as *Integration* → install **Proxmox Guest Updates** → restart Home Assistant.

Manual install: copy `custom_components/pveupdate` into your `/config/custom_components/` and restart.

### 3. Add it

Settings → Devices & services → **Add integration** → *Proxmox Guest Updates* → enter the host's IP, port `8765` and the token.

Options (⚙ on the integration): how often to check for updates, in hours (0 = only when you press *Check for updates*).

## Example: notify when updates are available

```yaml
automation:
  - alias: Proxmox updates available
    triggers:
      - trigger: numeric_state
        entity_id: sensor.proxmox_192_168_1_10_guests_with_updates
        above: 0
    actions:
      - action: notify.notify
        data:
          message: "{{ states('sensor.proxmox_192_168_1_10_guests_with_updates') }} Proxmox guests have updates"
```

## Notes

- The token is sent over plain HTTP, so keep port 8765 on your LAN (don't port-forward it). Rotate it with `pveupdate token --new`; Home Assistant will ask for the new one.
- Update output goes to `/var/log/pveupdate.log` on the host.
- Each guest's picture comes from the [selfh.st icon set](https://selfh.st/icons), matched by app or guest name (e.g. *zigbee2mqtt*, *mariadb*), then by OS (*debian*). Guests with no match use the integration's icon, which needs Home Assistant 2026.3 or newer.
- If a guest can't be snapshotted (storage without snapshot support), pveupdate takes a `vzdump` backup instead and then updates. If that fails too, the guest is skipped and the update entity shows why.
- Guests without a readable app version show their OS version (e.g. *Debian 12.11*) as the installed version. This needs pveupdate 0.4.0 or newer on the host.
