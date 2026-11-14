"""Blaupunkt LS 175 opt-in power control as an optimistic HA switch.

The physical remote has a single power TOGGLE command, not discrete on/off.
Home Assistant cannot read the soundbar's actual power state. The local state
may be out of sync if controlled from another remote, Bluetooth, or after a
power loss. Home Assistant switch.toggle always emits the real IR toggle.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .blaupunkt_ls175 import is_ls175_test_target
from .const import DOMAIN
from .coordinator import OrviboCloudCoordinator
from .ls175 import OrviboLS175TestEntity
from .selection import device_is_selected


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register one power switch for every selected compatible speaker."""
    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        OrviboLS175PowerSwitch(coordinator, device.uid)
        for device in coordinator.data.devices
        if is_ls175_test_target(device, coordinator.data.devices)
        and device_is_selected(entry.options, device.uid)
    )


class OrviboLS175PowerSwitch(OrviboLS175TestEntity, SwitchEntity, RestoreEntity):
    """Power switch whose state tracks the last acknowledged IR toggle locally.

    No ORVIBO feedback exists: the switch is optimistic and its state can
    disagree with the physical soundbar after external commands. The normal
    UI is a switch; status provenance is exposed in entity attributes.
    """

    _attr_name = "Power"
    _attr_icon = "mdi:power"
    _attr_should_poll = False
    # Home Assistant renders assumed_state=True switches as two separate
    # on/off buttons, not a slider. We expose the optimistic limitation in
    # attributes instead, so the user has an actual slider/toggle control.
    _attr_assumed_state = False

    def __init__(self, coordinator: OrviboCloudCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_ls175_beta_power_switch"
        # Initial position is only a UI estimate, not a claim about hardware.
        self._attr_is_on = False
        self._state_origin = "initial_estimate"

    async def async_added_to_hass(self) -> None:
        """Reuse only our own previous optimistic switch state, if present."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in (STATE_ON, STATE_OFF):
            self._attr_is_on = last.state == STATE_ON
            self._state_origin = "restored_estimate"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "state_source": self._state_origin,
            "physical_power_feedback": False,
            "ir_command": "power_toggle_0x00FFA25D",
            "caution": "Power state is estimated; other remotes may desynchronize it",
        }

    async def _async_toggle_power(self) -> None:
        """Send one physical toggle, update UI only after successful ACK."""
        await self._async_send_ls175(("power_toggle",))
        self._attr_is_on = not self._attr_is_on
        self._state_origin = "last_acknowledged_toggle"
        self.async_write_ha_state()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Always send the native IR toggle, regardless of our estimate."""
        await self._async_toggle_power()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Move the optimistic slider to ON using at most one IR toggle."""
        if not self.available:
            raise HomeAssistantError("ORVIBO LS175 target unavailable")
        if not self._attr_is_on:
            await self._async_toggle_power()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Move the optimistic slider to OFF using at most one IR toggle."""
        if not self.available:
            raise HomeAssistantError("ORVIBO LS175 target unavailable")
        if self._attr_is_on:
            await self._async_toggle_power()
