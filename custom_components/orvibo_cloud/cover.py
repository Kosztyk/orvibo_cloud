"""Curtain covers for Orvibo Cloud."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .binary import OrviboBinaryError, control_device
from .blind_state import AssumedBlindState, RFBlindOptions, configured_rf_blind_options
from .const import (
    CONF_FAMILY_ID,
    CONF_HOST,
    CONF_USER_ID,
    DOMAIN,
)
from .control import (
    OrviboControlCommand,
    curtain_position_command,
    curtain_position_from_orvibo,
    curtain_stop_command,
    is_rf_curtain,
    rf_curtain_command,
)
from .coordinator import OrviboCloudCoordinator
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


class OrviboCurtainCover(
    CoordinatorEntity[OrviboCloudCoordinator], CoverEntity, RestoreEntity
):
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
        self._optimistic_position: int | None = None
        self._control_lock = asyncio.Lock()
        self._rf_options = configured_rf_blind_options(coordinator.entry.options).get(
            device_id, RFBlindOptions()
        )
        self._assumed_blind_state = AssumedBlindState()
        self._cancel_expiry: Callable[[], None] | None = None
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

    async def async_added_to_hass(self) -> None:
        """Optionally restore command history and its original expiry deadline."""

        await super().async_added_to_hass()
        self.async_on_remove(self._async_cancel_expiry)
        if self._uses_rf_control and self._rf_options.restore:
            previous = await self.async_get_last_state()
            if previous is not None:
                self._assumed_blind_state = AssumedBlindState.from_attributes(
                    previous.attributes, dt_util.utcnow()
                )
        self._async_schedule_expiry()

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
        # RF-only blinds have no measured percentage. The device table's
        # placeholder value1=0 and a command acknowledgement are not positions.
        if self._uses_rf_control:
            return None
        if self._optimistic_position is not None:
            return self._optimistic_position
        device = self._device
        if device is None:
            return None
        return curtain_position_from_orvibo(device.value1)

    @property
    def is_closed(self) -> bool | None:
        if self._uses_rf_control:
            return self._assumed_blind_state.is_closed(
                self._rf_options, dt_util.utcnow()
            )
        position = self.current_cover_position
        return None if position is None else position == 0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._uses_rf_control or not self._rf_options.remember:
            return None
        return self._assumed_blind_state.attributes(self._rf_options, dt_util.utcnow())

    async def async_open_cover(self, **kwargs: Any) -> None:
        if self._uses_rf_control:
            await self._async_control(
                rf_curtain_command("open"), ha_position=None, rf_action="open"
            )
            return
        await self._async_control(curtain_position_command(100), ha_position=100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        if self._uses_rf_control:
            await self._async_control(
                rf_curtain_command("close"), ha_position=None, rf_action="close"
            )
            return
        await self._async_control(curtain_position_command(0), ha_position=0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        if self._uses_rf_control:
            await self._async_control(
                rf_curtain_command("stop"), ha_position=None, rf_action="stop"
            )
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
        *,
        rf_action: str | None = None,
    ) -> None:
        # Preserve command order when Open and Stop are requested together.
        async with self._control_lock:
            await self._async_send_control(command, ha_position, rf_action=rf_action)

    async def _async_send_control(
        self,
        command: OrviboControlCommand,
        ha_position: int | None,
        *,
        rf_action: str | None,
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
            self._optimistic_position = None
            if self._rf_options.remember and rf_action is not None:
                self._assumed_blind_state.record(rf_action, dt_util.utcnow())
                self._async_schedule_expiry()
        elif reported_position is not None:
            self._optimistic_position = reported_position
        elif ha_position is not None:
            self._optimistic_position = ha_position
        self.async_write_ha_state()

    @callback
    def _async_cancel_expiry(self) -> None:
        """Cancel the old deadline on a new command or when unloading the entity."""

        if self._cancel_expiry is not None:
            self._cancel_expiry()
            self._cancel_expiry = None

    @callback
    def _async_schedule_expiry(self) -> None:
        """Publish unknown at expiry even if no cloud refresh is received."""

        self._async_cancel_expiry()
        deadline = self._assumed_blind_state.expires_at(self._rf_options)
        if (
            self._uses_rf_control
            and self._rf_options.remember
            and self._assumed_blind_state.last_action in {"open", "close"}
            and deadline is not None
            and deadline > dt_util.utcnow()
        ):
            self._cancel_expiry = async_track_point_in_utc_time(
                self.hass, self._async_expire_assumption, deadline
            )

    @callback
    def _async_expire_assumption(self, now: datetime) -> None:
        """Retain diagnostic history while publishing an unknown cover state."""

        self._cancel_expiry = None
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._optimistic_position = None
        super()._handle_coordinator_update()
