# Proxmox Guest Updates for Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz)

Shows app updates for your Proxmox LXCs and VMs as Home Assistant **update** entities and installs them when you press **Install**. OS packages get their own *Update OS* button. Nothing updates on its own.

Works together with [pveupdate](https://github.com/Niiikoc/Pveupdate) **0.8.0 or later**, which runs on the Proxmox host and does the actual work: snapshot first, then OS packages (`apt`/`apk`), then the app's own update (community-scripts `update` or your own command).

It sits next to the regular Proxmox VE integrations; it doesn't replace them. The Proxmox API can't run commands inside containers, which is why pveupdate is needed on the host.

## What you get

- **One update entity per guest with an app**, e.g. *zigbee2mqtt: 2.9.1 → 2.14.2*, listed under Settings → Updates with an Install button and progress. Install takes a snapshot, then runs only the app's update.
- **On every guest's device page:** an *Update OS* button (snapshot, then OS packages only, which includes an app installed with apt), an *Update app* button for guests with an app (also works when the app's version can't be read, so the update entity can't tell whether there's a new one) and an *OS updates* sensor with the number of pending packages (attributes: security updates, package names, OS version, reboot required). OS packages never show up under Settings → Updates, so they don't nag you every day.
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

The API listens on port 8765 over HTTPS and requires the token for every request. It only accepts these actions: read status, list the node's guests, choose which are tracked, start a check, and update tracked guests.

### 2. Install the integration

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Niiikoc&repository=ha-pveupdate&category=integration)

HACS → search for **Proxmox Guest Updates** → **Download** → restart Home Assistant.

HACS installs the latest [release](https://github.com/Niiikoc/ha-pveupdate/releases) and tells you when a new one is out.

Manual install: download `pveupdate.zip` from the latest release, unzip it into `/config/custom_components/pveupdate/` and restart.

### 3. Add it

Settings → Devices & services → **Add integration** → *Proxmox Guest Updates* → enter the host's IP, port `8765` and the whole output of `pveupdate token`.

**Updating from an integration version before 0.4.0:** it stops working until you give it a new token, because it no longer connects without encryption. On the host, update pveupdate to 0.8.0 or later, then run `systemctl restart pveupdate-serve` and `pveupdate token`. Home Assistant asks for the new token under Settings → Devices & services. Your entities and automations stay as they are.

Options (⚙ on the integration):

- **Guests to track**: tick the LXCs and VMs pveupdate should manage. Newly ticked guests are checked right away; unticked ones are removed from Home Assistant.
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

- `pveupdate token` also prints the fingerprint of the host's certificate. Home Assistant connects only over HTTPS and trusts only that certificate, and it refuses a token without a fingerprint.
- Allow port 8765 only from Home Assistant's IP in the Proxmox firewall, and don't port-forward it. Home Assistant has no root access to the host, but anyone with the token can start updates on the guests, so turn on encryption for your Home Assistant backups, which contain it.
- Rotate the token with `pveupdate token --new`. The old one stops working immediately and Home Assistant asks for the new one. It also asks if the host's certificate changes.
- `pveupdate set default --remote-track off` on the host limits the token to the guests you chose there; Home Assistant then can't change them.
- Update output goes to `/var/log/pveupdate.log` on the host.
- Each guest's picture comes from the [selfh.st icon set](https://selfh.st/icons), matched by app or guest name (e.g. *zigbee2mqtt*, *mariadb*), then by OS (*debian*). Guests with no match use the integration's icon, which needs Home Assistant 2026.3 or newer.
- If a guest can't be snapshotted (storage without snapshot support), pveupdate takes a `vzdump` backup instead and then updates. If that fails too, the guest is skipped and the update entity shows why.

## Contributing

Issues and pull requests are welcome. Changes reach `master` only through a pull request that passes the checks and is merged by the maintainer, and users only get them once they're in a release. A release is published automatically when a merge changes the version in `manifest.json`.
