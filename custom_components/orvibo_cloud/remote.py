"""Named TV remote commands for ORVIBO Allone Pro."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import RemoteEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .control import is_allone_tv, tv_commands_for_profile
from .coordinator import OrviboCloudCoordinator
from .selection import device_is_selected
from .tv import OrviboTVEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a remote for each selected Allone Pro TV."""

    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        OrviboTVRemote(coordinator, device.uid)
        for device in coordinator.data.devices
        if is_allone_tv(device, coordinator.data.devices)
        and device_is_selected(entry.options, device.uid)
    )


class OrviboTVRemote(OrviboTVEntity, RemoteEntity):
    """Send the app's stored TV keys through remote.send_command."""

    _attr_name = "Remote"
    _attr_icon = "mdi:remote-tv"
    _attr_is_on = None
    _attr_assumed_state = True

    def __init__(
        self,
        coordinator: OrviboCloudCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_tv_remote"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """List accepted command names without inventing TV power feedback."""

        return {
            "commands": [command.key for command in tv_commands_for_profile(
                self.coordinator.entry.options.get("tv_profile", "lg")
            )],
            "tv_profile": self.coordinator.entry.options.get("tv_profile", "lg"),
            "power_control": "toggle_only",
        }

    async def async_send_command(
        self, command: Iterable[str], **kwargs: Any
    ) -> None:
        """Send a validated command sequence; learning and holds are unsupported."""

        if kwargs.get("device"):
            raise HomeAssistantError("Target the TV's own remote entity")
        await self._async_send_tv_commands(
            command,
            num_repeats=kwargs.get("num_repeats", 1),
            delay_secs=kwargs.get("delay_secs", 0.4),
            hold_secs=kwargs.get("hold_secs", 0),
        )

    async def async_toggle(self, **kwargs: Any) -> None:
        """Send the single power key supplied by this TV profile."""

        await self._async_send_tv_commands(("power_toggle",))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Do not present a power toggle as a guaranteed power-on command."""

        raise HomeAssistantError(
            "This TV has a power toggle only; use the Power toggle button "
            "or remote.send_command with power_toggle"
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Do not present a power toggle as a guaranteed power-off command."""

        await self.async_turn_on(**kwargs)
