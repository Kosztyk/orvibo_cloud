"""Visible TV remote buttons for ORVIBO Allone Pro."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .control import OrviboTVCommand, is_allone_tv, tv_commands_for_profile
from .coordinator import OrviboCloudCoordinator
from .selection import device_is_selected
from .tv import OrviboTVEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose the stored TV keys for each selected Allone Pro TV."""

    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        OrviboTVButton(coordinator, device.uid, command)
        for device in coordinator.data.devices
        if is_allone_tv(device, coordinator.data.devices)
        and device_is_selected(entry.options, device.uid)
        for command in tv_commands_for_profile(entry.options.get("tv_profile", "lg"))
    )


class OrviboTVButton(OrviboTVEntity, ButtonEntity):
    """Send a single stored infrared key without assuming television state."""

    def __init__(
        self,
        coordinator: OrviboCloudCoordinator,
        device_id: str,
        command: OrviboTVCommand,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._command = command.key
        self._attr_unique_id = f"{device_id}_tv_{command.key}"
        self._attr_name = command.name
        self._attr_icon = command.icon

    async def async_press(self) -> None:
        """Transmit exactly one key using the TV child ID and its hub UID."""

        await self._async_send_tv_commands((self._command,))
