"""Curtain covers for Orvibo Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .binary import OrviboBinaryError, control_device
from .const import (
    CONF_FAMILY_ID,
    CONF_HOST,
    CONF_USER_ID,
    DOMAIN,
)
from .coordinator import OrviboCloudCoordinator
from .control import (
    OrviboControlCommand,
    curtain_position_command,
    curtain_position_from_orvibo,
    curtain_stop_command,
    is_rf_curtain,
    rf_curtain_command,
)
from .protocol import OrviboDevice
from .selection import device_is_selected

_CURTAIN_DEVICE_TYPE = "34"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up every supported curtain returned by ORVIBO Cloud."""

    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        OrviboCurtainCover(coordinator, device.uid)
        for device in coordinator.data.devices
        if device.device_type == _CURTAIN_DEVICE_TYPE
        and device_is_selected(entry.options, device.uid)
    )


class OrviboCurtainCover(CoordinatorEntity[OrviboCloudCoordinator], CoverEntity):
    """Control one ORVIBO type-34 curtain motor."""

    _attr_device_class = CoverDeviceClass.CURTAIN
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(
        self,
        coordinator: OrviboCloudCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._assumed_position: int | None = None
        self._optimistic_position: int | None = None
        self._attr_unique_id = f"{device_id}_cover"
        device = self._device
        assert device is not None
        account_identifier = (DOMAIN, coordinator.entry.data[CONF_USER_ID])
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="ORVIBO",
            model=device.model or "Curtain",
            name=device.name or "ORVIBO Curtain",
            suggested_area=device.room or None,
            via_device=account_identifier,
        )

    @property
    def _device(self) -> OrviboDevice | None:
        return next(
            (
                device
                for device in self.coordinator.data.devices
                if device.uid == self._device_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        device = self._device
        return (
            super().available
            and device is not None
            and device.online is not False
            and bool(self.coordinator.data.binary_password)
        )

    @property
    def _uses_rf_control(self) -> bool:
        device = self._device
        return device is not None and is_rf_curtain(
            device, self.coordinator.data.devices
        )

    @property
    def supported_features(self) -> CoverEntityFeature:
        if self._uses_rf_control:
            return (
                CoverEntityFeature.OPEN
                | CoverEntityFeature.CLOSE
                | CoverEntityFeature.STOP
            )
        return self._attr_supported_features

    @property
    def assumed_state(self) -> bool:
        return self._uses_rf_control

    @property
    def current_cover_position(self) -> int | None:
        # RF-only blinds have no measured percentage. The device table's placeholder value1=0 
        # and a command acknowledgement are not positions.  Here we assume a position based on
        # the last action called on the RF blind, acknowledging that this is not 100% fool-proof
        if self._uses_rf_control:
            return self._assumed_position
        if self._optimistic_position is not None:
            return self._optimistic_position
        device = self._device
        if device is None:
            return None
        return curtain_position_from_orvibo(device.value1)

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        return None if position is None else position == 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        if self._uses_rf_control:
            # Opening, so ha_position is 1
            await self._async_control(rf_curtain_command("open"), ha_position=1)
            return
        await self._async_control(curtain_position_command(100), ha_position=100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        if self._uses_rf_control:
            # Closing, so ha_position is 0
            await self._async_control(rf_curtain_command("close"), ha_position=0)
            return
        await self._async_control(curtain_position_command(0), ha_position=0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        if self._uses_rf_control:
            # Stopping, so ha_position is None
            await self._async_control(rf_curtain_command("stop"), ha_position=None)
            return
        await self._async_control(curtain_stop_command(), ha_position=None)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        if self._uses_rf_control:
            raise HomeAssistantError(
                "This RF blind supports Open, Close, and Stop only"
            )
        ha_position = max(0, min(100, int(kwargs[ATTR_POSITION])))
        await self._async_control(curtain_position_command(ha_position), ha_position)

    async def _async_control(
        self,
        command: OrviboControlCommand,
        ha_position: int | None,
    ) -> None:
        entry_data = self.coordinator.entry.data
        device = self._device
        if device is None or not device.cloud_uid:
            raise HomeAssistantError("ORVIBO control identifiers are missing")
        try:
            reported_values = await self.hass.async_add_executor_job(
                control_device,
                entry_data[CONF_HOST],
                self.coordinator.data.binary_user_name,
                self.coordinator.data.binary_password,
                entry_data[CONF_FAMILY_ID],
                self._device_id,
                device.cloud_uid,
                command.order,
                command.value1,
                command.value2,
                command.value3,
                command.value4,
            )
        except (OrviboBinaryError, OSError, TimeoutError) as err:
            raise HomeAssistantError(str(err)) from err

        reported_position = curtain_position_from_orvibo(reported_values[0])
        if self._uses_rf_control:
            # ha_position is non-zero when action is open, 0 when close, and None when stop
            #   Set the self._assumed_position flag based off of this
            self._assumed_position = ha_position
        elif reported_position is not None:
            self._optimistic_position = reported_position
        elif ha_position is not None:
            self._optimistic_position = ha_position
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._optimistic_position = None
        super()._handle_coordinator_update()
