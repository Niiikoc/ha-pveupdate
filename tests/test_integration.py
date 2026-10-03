"""Tests against a mocked `pveupdate serve` API."""

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pveupdate.const import DOMAIN

BASE = "http://pve.local:8765/api"
DATA = {CONF_HOST: "pve.local", CONF_PORT: 8765, CONF_TOKEN: "secret"}


def status(**over):
    s = {
        "version": "0.3.0",
        "checked_at": dt_util.utcnow().isoformat(),
        "running": False,
        "activity": None,
        "updating": None,
        "queue": [],
        "pending_guests": 2,
        "pending_ids": "101 105",
        "guests": {
            "101": {"name": "mqtt", "type": "lxc", "state": "ok", "os": "Debian 12.11", "packages": 3, "app": None,
                    "app_installed": None, "app_latest": None, "app_update": False, "pending": True,
                    "package_names": ["libc6", "openssl", "mosquitto"], "reboot_required": False},
            "102": {"name": "mariadb", "type": "lxc", "state": "ok", "packages": 0, "app": None,
                    "app_installed": None, "app_latest": None, "app_update": False, "pending": False,
                    "package_names": [], "reboot_required": False},
            "105": {"name": "zigbee2mqtt", "type": "lxc", "state": "ok", "packages": 2, "app": "zigbee2mqtt",
                    "app_installed": "2.9.1", "app_latest": "2.14.2", "app_update": True, "pending": True,
                    "package_names": ["libc6", "openssl"], "reboot_required": False},
        },
    }
    s.update(over)
    return s


async def setup(hass, aioclient_mock, st=None):
    aioclient_mock.get(f"{BASE}/status", json=st or status())
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="pve.local:8765")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/status", json=status())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == DATA


async def test_config_flow_bad_token(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/status", status=401, json={"error": "invalid or missing token"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_unreachable(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/status", exc=TimeoutError())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_entities(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock)
    z = hass.states.get("update.zigbee2mqtt")
    assert z.state == "on"
    assert z.attributes["installed_version"] == "2.9.1"
    assert z.attributes["latest_version"] == "2.14.2 + 2 packages"
    assert "2.9.1 → 2.14.2" in z.attributes["release_summary"]
    m = hass.states.get("update.mqtt")
    assert m.state == "on"
    assert m.attributes["installed_version"] == "Debian 12.11"
    assert m.attributes["latest_version"] == "Debian 12.11 + 3 packages"
    mdb = hass.states.get("update.mariadb")
    assert mdb.state == "off"
    assert mdb.attributes["installed_version"] == "current"  # older pveupdate without `os`
    assert hass.states.get("sensor.proxmox_pve_local_guests_with_updates").state == "2"
    assert hass.states.get("sensor.proxmox_pve_local_activity").state == "idle"


async def test_install(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock)
    aioclient_mock.post(f"{BASE}/update", status=202, json={"started": "update", "guests": ["105"]})
    await hass.services.async_call("update", "install", {"entity_id": "update.zigbee2mqtt"}, blocking=True)
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert posts and str(posts[-1][1]).endswith("/api/update")
    assert posts[-1][2] == {"guests": ["105"]}


async def test_in_progress(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock, status(running=True, activity="updating", updating="101", queue=["105"]))
    assert hass.states.get("update.mqtt").attributes["in_progress"] is True
    assert hass.states.get("update.zigbee2mqtt").attributes["in_progress"] is True
    assert hass.states.get("update.mariadb").attributes["in_progress"] is False
    assert hass.states.get("sensor.proxmox_pve_local_activity").state == "updating"


async def test_check_started_when_stale(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.post(f"{BASE}/check", status=202, json={"started": "check"})
    await setup(hass, aioclient_mock, status(checked_at=None))
    assert any(c[0] == "POST" and str(c[1]).endswith("/api/check") for c in aioclient_mock.mock_calls)


async def test_buttons(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock)
    aioclient_mock.post(f"{BASE}/update", status=202, json={"started": "update"})
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.proxmox_pve_local_update_all_pending"}, blocking=True
    )
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert posts[-1][2] == {"guests": "pending"}


async def test_skip_reason_shown(hass: HomeAssistant, aioclient_mock):
    st = status()
    st["guests"]["101"].update(last_result="skipped", last_detail="no snapshot (snapshot feature is not available) or backup (no storage)")
    await setup(hass, aioclient_mock, st)
    m = hass.states.get("update.mqtt")
    assert "last update skipped: no snapshot" in m.attributes["release_summary"]
    assert m.attributes["last_detail"].startswith("no snapshot")
