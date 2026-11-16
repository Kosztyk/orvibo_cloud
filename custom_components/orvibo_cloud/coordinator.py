"""Data update coordinator for Orvibo Cloud."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OrviboAccount,
    OrviboCannotConnectError,
    OrviboCloudClient,
    OrviboInvalidAuthError,
    OrviboProtocolError,
)
from .binary import OrviboServerIdentityError, load_binary_server_pins
from .capture import OrviboRawEventCapture
from .const import (
    CONF_FAMILY_ID,
    CONF_HOST,
    CONF_PASSWORD_HASH,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class OrviboCloudCoordinator(DataUpdateCoordinator[OrviboAccount]):
    """Refresh the Orvibo access token and family metadata."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: OrviboCloudClient,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.entry = entry
        self.client = client
        self.device_discovery_error: str | None = None
        self.privacy_device_discovery_error: str | None = None
        self.raw_event_capture: OrviboRawEventCapture | None = None
        self.tv_control_lock = asyncio.Lock()
        self.tv_sequence_lock = asyncio.Lock()
        self.door_status_signal = f"{DOMAIN}_{entry.entry_id}_door_status"
        self.last_push_reconnect_ns = 0
        self.binary_server_trust = "vendor_ca"

    @callback
    def async_resync_doors(self, reconnected_ns: int) -> None:
        """Invalidate observations from the previous stream and refresh the table."""
        self.last_push_reconnect_ns = reconnected_ns
        self.async_update_listeners()
        self.entry.async_create_task(
            self.hass, self.async_request_refresh(), f"{DOMAIN} refresh door state"
        )

    async def _async_setup(self) -> None:
        """Check any optional server pins before the first cloud refresh."""
        try:
            pins = await self.hass.async_add_executor_job(
                load_binary_server_pins, self.entry.data[CONF_HOST]
            )
        except OrviboServerIdentityError as err:
            self.binary_server_trust = "invalid_pin"
            _LOGGER.warning("ORVIBO binary control unavailable: %s", err)
            return
        self.binary_server_trust = "pin_configured" if pins else "vendor_ca"

    async def _async_update_data(self) -> OrviboAccount:
        try:
            account = await self.client.async_discover(
                email=self.entry.data[CONF_EMAIL],
                password_md5=self.entry.data[CONF_PASSWORD_HASH],
                hosts=(self.entry.data[CONF_HOST],),
                family_id=self.entry.data[CONF_FAMILY_ID],
            )
        except OrviboInvalidAuthError as err:
            raise ConfigEntryAuthFailed from err
        except (OrviboCannotConnectError, OrviboProtocolError) as err:
            self.device_discovery_error = "discovery_failed"
            raise UpdateFailed(str(err)) from err

        self.device_discovery_error = None
        self.privacy_device_discovery_error = None
        if self.binary_server_trust == "invalid_pin":
            return replace(account, binary_user_name="", binary_password="")
        return account
