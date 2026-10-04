# Proxmox Guest Updates for Home Assistant

Shows app updates for your Proxmox LXCs and VMs as Home Assistant **update** entities and installs them when you press **Install**. OS packages get their own *Update OS* button. Nothing updates on its own.

Works together with [pveupdate](https://github.com/Niiikoc/Pveupdate), which runs on the Proxmox host and does the actual work: snapshot first, then OS packages (`apt`/`apk`), then the app's own update (community-scripts `update` or your own command).

It sits next to the regular Proxmox VE integrations; it doesn't replace them. The Proxmox API can't run commands inside containers, which is why pveupdate is needed on the host.

## What you get

- **One update entity per guest with an app**, e.g. *zigbee2mqtt: 2.9.1 → 2.14.2*, listed under Settings → Updates with an Install button and progress. Install takes a snapshot, then runs only the app's update.
- **On every guest's device page:** an *Update OS* button (snapshot, then OS packages only), an *Update app* button for guests with an app (also works when the app's version can't be read, so the update entity can't tell whether there's a new one) and an *OS updates* sensor with the number of pending packages (attributes: security updates, package names, OS version, reboot required). OS packages never show up under Settings → Updates, so they don't nag you every day.
- **Proxmox host device** with:
  - *Check for updates* button
  - *Update all pending* updates both the OS and the app of every guest with updates
  - *Guests with updates* sensor: guests with an app update (optional, for your own automations)
  - *Last check* and *Activity* (idle / checking / updating) sensors
- Automatic read-only checks every 6 hours (configurable, or off).

## Setup

### 1. On the Proxmox host

```bash
base=https://github.com/Niiikoc/Pveupdate/releases/latest/download
curl -fsSL $base/pveupdate.py -o /usr/local/bin/pveupdate && chmod +x /usr/local/bin/pveupdate
pveupdate track                      # choose the guests to manage (or later from Home Assistant)

curl -fsSL $base/pveupdate-serve.service -o /etc/systemd/system/pveupdate-serve.service
systemctl daemon-reload && systemctl enable --now pveupdate-serve
pveupdate token                      # copy this for step 3
```

The API listens on port 8765 and requires the token for every request. It only accepts these actions: read status, list the node's guests, choose which are tracked, start a check, and update tracked guests.

### 2. Install the integration

HACS → ⋮ → **Custom repositories** → add `https://github.com/Niiikoc/ha-pveupdate` as *Integration* → install **Proxmox Guest Updates** → restart Home Assistant.

HACS installs the latest [release](https://github.com/Niiikoc/ha-pveupdate/releases) and tells you when a new one is out.

Manual install: download `pveupdate.zip` from the latest release, unzip it into `/config/custom_components/pveupdate/` and restart.

### 3. Add it

Settings → Devices & services → **Add integration** → *Proxmox Guest Updates* → enter the host's IP, port `8765` and the token.

Options (⚙ on the integration):

- **Guests to track**: tick the LXCs and VMs pveupdate should manage. Newly ticked guests are checked right away; unticked ones are removed from Home Assistant. Needs pveupdate 0.6.0 or later on the host.
- How often to check for updates, in hours (0 = only when you press *Check for updates*).

## Optional: a notification

You don't need any automation: every guest with an app update shows up under **Settings → Updates**, like Home Assistant's own updates. If you also want a phone notification, this example uses the *Guests with updates* sensor:

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

Replace `192_168_1_10` with your host as it appears in the sensor's entity ID.

## Notes

- The token is sent over plain HTTP, so keep port 8765 on your LAN (don't port-forward it). Rotate it with `pveupdate token --new`; Home Assistant will ask for the new one.
- Update output goes to `/var/log/pveupdate.log` on the host.
- Each guest's picture comes from the [selfh.st icon set](https://selfh.st/icons), matched by app or guest name (e.g. *zigbee2mqtt*, *mariadb*), then by OS (*debian*). Guests with no match use the integration's icon, which needs Home Assistant 2026.3 or newer.
- If a guest can't be snapshotted (storage without snapshot support), pveupdate takes a `vzdump` backup instead and then updates. If that fails too, the guest is skipped and the update entity shows why.
- Separate app and OS updates need pveupdate 0.7.0 or newer on the host. With an older one, Install and *Update OS* ask you to update pveupdate first.

## Contributing

Issues and pull requests are welcome. Changes reach `master` only through a pull request that passes the checks and is merged by the maintainer, and users only get them once they're in a release. A release is published automatically when a merge changes the version in `manifest.json`.
