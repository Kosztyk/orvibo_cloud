"""Visible TV remote buttons for ORVIBO Allone Pro."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .blaupunkt_ls175 import LS175_CONFIRMED_KEYS, is_ls175_test_target
from .ls175 import OrviboLS175TestEntity
from .const import DOMAIN
from .control import OrviboTVCommand, is_allone_tv, tv_commands_for_profile
from .coordinator import OrviboCloudCoordinator
from .selection import (
    SPEAKER_MODEL_BLAUPUNKT_LS175, device_is_selected,
    speaker_ir_profile_is_selected,
)
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
    # LS175 is opt-in per speaker, and never sends IR during registration.
    async_add_entities(
        OrviboLS175TestButton(coordinator, device.uid, key)
        for device in coordinator.data.devices
        if is_ls175_test_target(device, coordinator.data.devices)
        and device_is_selected(entry.options, device.uid)
        for key in LS175_CONFIRMED_KEYS
        if key.key != "code_07"  # Power is now a native switch, not a button.
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


class OrviboLS175TestButton(OrviboLS175TestEntity, ButtonEntity):
    """One manually initiated, physically verified LS175 command."""

    def __init__(self, coordinator, device_id: str, key) -> None:
        super().__init__(coordinator, device_id)
        self._key = key.key
        self._attr_unique_id = f"{device_id}_ls175_beta_{key.key}"
        self._attr_name = key.label
        self._attr_icon = {
            "code_02": "mdi:volume-plus",
            "code_03": "mdi:volume-minus",
            "code_06": "mdi:video-input-hdmi",
            "code_08": "mdi:equalizer",
            "code_10": "mdi:volume-mute",
        }.get(self._key, "mdi:remote")

    async def async_press(self) -> None:
        await self._async_send_ls175((self._key,))
