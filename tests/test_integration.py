"""Tests against a mocked `pveupdate serve` API."""

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pveupdate.const import DOMAIN

BASE = "http://pve.local:8765/api"
DATA = {CONF_HOST: "pve.local", CONF_PORT: 8765, CONF_TOKEN: "secret"}


def status(**over):
    s = {
        "version": "0.7.0",
        "checked_at": dt_util.utcnow().isoformat(),
        "running": False,
        "activity": None,
        "updating": None,
        "updating_part": None,
        "queue": [],
        "pending_guests": 4,
        "pending_ids": "101 102 103 105",
        "guests": {
            "101": {"name": "mqtt", "type": "lxc", "state": "ok", "os": "Debian 12.11", "packages": 3, "app": "mqtt",
                    "app_installed": "2.0.18", "app_latest": "2.0.18", "app_update": False, "pending": True,
                    "package_names": ["libc6", "openssl", "mosquitto"], "security_packages": 1,
                    "reboot_required": False},
            "102": {"name": "mariadb", "type": "lxc", "state": "ok", "packages": 0, "app": "mariadb",
                    "app_installed": None, "app_latest": None, "app_update": False, "pending": False,
                    "package_names": [], "reboot_required": False},
            "103": {"name": "plain", "type": "lxc", "state": "ok", "os": "Debian 12.11", "os_latest": "Debian 12.12",
                    "packages": 4, "app": None, "app_installed": None, "app_latest": None, "app_update": False,
                    "pending": True, "package_names": ["a", "b", "c", "d"], "security_packages": 2,
                    "reboot_required": False},
            "105": {"name": "zigbee2mqtt", "type": "lxc", "state": "ok", "packages": 2, "app": "zigbee2mqtt",
                    "app_installed": "2.9.1", "app_latest": "2.14.2", "app_update": True, "pending": True,
                    "package_names": ["libc6", "openssl"], "reboot_required": False},
        },
    }
    s.update(over)
    return s


ICONS = "https://cdn.jsdelivr.net/gh/selfhst/icons/png"


def mock_icons(aioclient_mock):
    for name, code in {"zigbee2mqtt": 200, "mosquitto": 404, "debian": 200, "mariadb": 404}.items():
        aioclient_mock.head(f"{ICONS}/{name}.png", status=code)


async def setup(hass, aioclient_mock, st=None):
    mock_icons(aioclient_mock)
    aioclient_mock.get(f"{BASE}/status", json=st or status())
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="pve.local:8765")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, aioclient_mock):
    mock_icons(aioclient_mock)
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
    # Settings > Updates: app updates only.
    z = hass.states.get("update.zigbee2mqtt")
    assert z.state == "on"
    assert z.attributes["installed_version"] == "2.9.1"
    assert z.attributes["latest_version"] == "2.14.2"
    assert "2.9.1 → 2.14.2" in z.attributes["release_summary"]
    m = hass.states.get("update.mqtt")
    assert m.state == "off"  # OS packages pending, but no app update
    assert m.attributes["installed_version"] == "2.0.18"
    assert hass.states.get("update.mariadb").attributes["installed_version"] == "unknown"  # no app or OS version
    assert hass.states.get("update.plain") is None  # no app
    assert hass.states.get("sensor.proxmox_pve_local_guests_with_updates").state == "1"
    assert hass.states.get("sensor.proxmox_pve_local_activity").state == "idle"
    # OS packages: a sensor and a button on every guest.
    p = hass.states.get("sensor.plain_os_updates")
    assert p.state == "4"
    assert p.attributes["security_packages"] == 2
    assert p.attributes["os_latest"] == "Debian 12.12"
    assert hass.states.get("sensor.mqtt_os_updates").state == "3"
    assert hass.states.get("sensor.mariadb_os_updates").state == "0"
    assert hass.states.get("button.plain_update_os")
    assert hass.states.get("button.zigbee2mqtt_update_os")
    # Update app: every guest with an app, none without.
    assert hass.states.get("button.zigbee2mqtt_update_app")
    assert hass.states.get("button.plain_update_app") is None


async def test_install(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock)
    aioclient_mock.post(f"{BASE}/update", status=202, json={"started": "update", "guests": ["105"]})
    await hass.services.async_call("update", "install", {"entity_id": "update.zigbee2mqtt"}, blocking=True)
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert posts and str(posts[-1][1]).endswith("/api/update")
    assert posts[-1][2] == {"guests": ["105"], "part": "app"}


async def test_update_os_button(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock)
    aioclient_mock.post(f"{BASE}/update", status=202, json={"started": "update", "guests": ["101"]})
    await hass.services.async_call("button", "press", {"entity_id": "button.mqtt_update_os"}, blocking=True)
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert posts[-1][2] == {"guests": ["101"], "part": "os"}


async def test_unknown_app_version(hass: HomeAssistant, aioclient_mock):
    """An app whose version can't be read shows the OS version and can be updated with its button."""
    st = status()
    st["guests"]["101"].update(app_installed=None, app_latest=None)
    await setup(hass, aioclient_mock, st)
    assert hass.states.get("update.mqtt").attributes["installed_version"] == "Debian 12.11"
    aioclient_mock.post(f"{BASE}/update", status=202, json={"started": "update", "guests": ["101"]})
    await hass.services.async_call("button", "press", {"entity_id": "button.mqtt_update_app"}, blocking=True)
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert posts[-1][2] == {"guests": ["101"], "part": "app"}


async def test_old_host_refuses_split(hass: HomeAssistant, aioclient_mock):
    """pveupdate before 0.7.0 ignores "part" and would update both, so don't send it."""
    await setup(hass, aioclient_mock, status(version="0.6.1"))
    for domain, service, entity in [("update", "install", "update.zigbee2mqtt"), ("button", "press", "button.mqtt_update_os")]:
        with pytest.raises(HomeAssistantError, match="0.7.0"):
            await hass.services.async_call(domain, service, {"entity_id": entity}, blocking=True)
    assert not [c for c in aioclient_mock.mock_calls if c[0] == "POST" and str(c[1]).endswith("/update")]


async def test_in_progress(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock, status(running=True, activity="updating", updating="105", updating_part="app",
                                             queue=["101"], progress=45, step="app"))
    z = hass.states.get("update.zigbee2mqtt")
    assert z.attributes["in_progress"] is True
    assert z.attributes["update_percentage"] == 45
    assert z.attributes["update_step"] == "app"
    m = hass.states.get("update.mqtt")
    assert m.attributes["in_progress"] is True
    assert m.attributes["update_percentage"] is None  # queued
    assert hass.states.get("update.mariadb").attributes["in_progress"] is False
    assert hass.states.get("sensor.proxmox_pve_local_activity").state == "updating"


async def test_os_update_not_shown_as_app_update(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock, status(running=True, activity="updating", updating="105", updating_part="os",
                                             progress=30, step="os"))
    assert hass.states.get("update.zigbee2mqtt").attributes["in_progress"] is False
    assert hass.states.get("sensor.zigbee2mqtt_os_updates").attributes["updating"] is True


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
    st["guests"]["105"].update(last_result="skipped", last_detail="no snapshot (snapshot feature is not available) or backup (no storage)")
    await setup(hass, aioclient_mock, st)
    z = hass.states.get("update.zigbee2mqtt")
    assert "last update skipped: no snapshot" in z.attributes["release_summary"]
    assert z.attributes["last_detail"].startswith("no snapshot")


async def test_guest_pictures(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock)
    # App icon when one exists.
    assert hass.states.get("update.zigbee2mqtt").attributes["entity_picture"] == f"{ICONS}/zigbee2mqtt.png"
    # No icon for the app ("mqtt" -> mosquitto 404): falls back to its OS.
    assert hass.states.get("update.mqtt").attributes["entity_picture"] == f"{ICONS}/debian.png"
    # Nothing found: the integration's own icon.
    assert hass.states.get("update.mariadb").attributes["entity_picture"].endswith("/pveupdate/icon.png")


async def test_old_update_entity_removed(hass: HomeAssistant, aioclient_mock):
    """0.2.x gave guests without an app an update entity; it goes away."""
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="pve.local:8765")
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create("update", DOMAIN, f"{entry.entry_id}_103_update", config_entry=entry,
                                 suggested_object_id="plain")
    mock_icons(aioclient_mock)
    aioclient_mock.get(f"{BASE}/status", json=status())
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("update", DOMAIN, f"{entry.entry_id}_103_update") is None
    assert hass.states.get("update.plain") is None


GUESTS = [
    {"id": "101", "type": "lxc", "name": "mqtt", "status": "running", "tracked": True},
    {"id": "102", "type": "lxc", "name": "mariadb", "status": "running", "tracked": True},
    {"id": "105", "type": "lxc", "name": "zigbee2mqtt", "status": "running", "tracked": True},
    {"id": "200", "type": "vm", "name": "haos", "status": "running", "tracked": False},
]


async def test_options_choose_guests(hass: HomeAssistant, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    assert hass.states.get("update.mariadb")
    aioclient_mock.get(f"{BASE}/guests", json={"guests": GUESTS})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert "guests" in result["data_schema"].schema

    # Untrack mariadb, track the haos VM. The host then reports the new set.
    st = status()
    st["guests"].pop("102")
    st["guests"]["200"] = {"name": "haos", "type": "vm", "state": "unchecked", "packages": 0, "app": None,
                           "app_installed": None, "app_latest": None, "app_update": False, "pending": False,
                           "package_names": [], "reboot_required": False}
    aioclient_mock.clear_requests()
    mock_icons(aioclient_mock)
    aioclient_mock.head(f"{ICONS}/home-assistant.png", status=200)
    aioclient_mock.get(f"{BASE}/guests", json={"guests": GUESTS})
    aioclient_mock.get(f"{BASE}/status", json=st)
    aioclient_mock.post(f"{BASE}/track", json={"tracked": ["101", "105", "200"]})
    aioclient_mock.post(f"{BASE}/check", status=202, json={"started": "check"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"guests": ["101", "105", "200"], "check_interval": 6}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"check_interval": 6}
    posts = {str(c[1]).rsplit("/", 1)[-1]: c[2] for c in aioclient_mock.mock_calls if c[0] == "POST"}
    assert posts["track"] == {"guests": ["101", "105", "200"]}
    assert "check" in posts
    assert hass.states.get("sensor.haos_os_updates")
    assert hass.states.get("update.haos") is None  # no app
    assert hass.states.get("update.mariadb") is None
    assert hass.states.get("sensor.mariadb_os_updates") is None


async def test_options_old_host(hass: HomeAssistant, aioclient_mock):
    """A pveupdate without /api/guests still lets you change the interval."""
    entry = await setup(hass, aioclient_mock)
    aioclient_mock.get(f"{BASE}/guests", status=404, json={"error": "not found"})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["errors"] == {"base": "cannot_list_guests"}
    assert "guests" not in result["data_schema"].schema
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"check_interval": 12})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"check_interval": 12}
