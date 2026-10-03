"""Constants for the Proxmox Guest Updates integration."""

from datetime import timedelta

DOMAIN = "pveupdate"

DEFAULT_PORT = 8765
CONF_CHECK_INTERVAL = "check_interval"
CONF_GUESTS = "guests"
DEFAULT_CHECK_INTERVAL = 6  # hours; 0 disables automatic checks

SCAN_INTERVAL = timedelta(seconds=60)
# Poll faster while a check or update runs, so progress shows quickly.
FAST_SCAN_INTERVAL = timedelta(seconds=5)
