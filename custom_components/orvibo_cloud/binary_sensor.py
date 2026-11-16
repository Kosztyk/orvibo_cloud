"""Binary sensors for Orvibo Cloud."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_USER_ID, DOMAIN
from .coordinator import OrviboCloudCoordinator
from .entity import OrviboCloudDeviceEntity, OrviboCloudEntity
from .protocol import OrviboDevice, property_switch_state, protocol_update_time
from .selection import device_is_selected


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        OrviboCloudConnectionBinarySensor(coordinator)
    ]
    entities.extend(
        OrviboDoorBinarySensor(coordinator, device.uid)
        for device in coordinator.data.devices
        if device_is_selected(entry.options, device.uid)
        and "door_status" in device.properties
    )
    async_add_entities(entities)


class OrviboCloudConnectionBinarySensor(OrviboCloudEntity, BinarySensorEntity):
    """Report whether the latest authenticated refresh succeeded."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "connection"

    def __init__(self, coordinator: OrviboCloudCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.data[CONF_USER_ID]}_connection"

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


@dataclass(frozen=True, slots=True)
class _DoorObservation:
    is_open: bool
    received_ns: int
    update_time: int | None

    def is_newer(self, other_received_ns: int, other_update_time: int | None) -> bool:
        if self.update_time is not None and other_update_time is not None:
            return (self.update_time, self.received_ns) > (
                other_update_time, other_received_ns
            )
        return self.received_ns > other_received_ns


class OrviboDoorBinarySensor(OrviboCloudDeviceEntity, BinarySensorEntity):
    """Report the open/closed state of a property-based door lock."""

    _attr_device_class = BinarySensorDeviceClass.DOOR
    _attr_name = "Door"

    def __init__(
        self,
        coordinator: OrviboCloudCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_door"
        self._door_push: _DoorObservation | None = None
        self.async_on_remove(
            async_dispatcher_connect(
                coordinator.hass,
                coordinator.door_status_signal,
                self._handle_lock_event,
            )
        )

    @property
    def is_on(self) -> bool | None:
        device = self._device
        if device is None:
            return None
        if self._door_push is not None and self._is_current(self._door_push, device):
            return self._door_push.is_open
        return property_switch_state(device.properties, "door_status")

    def _is_current(self, observation: _DoorObservation, device: OrviboDevice) -> bool:
        return (
            observation.received_ns > self.coordinator.last_push_reconnect_ns
            and observation.is_newer(
                self.coordinator.data.device_snapshot_started_ns, device.status_update_time
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        device = self._device
        if self._door_push is not None and (
            device is None or not self._is_current(self._door_push, device)
        ):
            self._door_push = None
        super()._handle_coordinator_update()

    @callback
    def _handle_lock_event(self, event: Mapping[str, Any], received_ns: int) -> None:
        if self._device_id not in (event.get("device_id"), event.get("uid")):
            return
        door_state = event.get("door_state")
        if door_state not in {"open", "closed"}:
            return
        observation = _DoorObservation(
            door_state == "open", received_ns, protocol_update_time(event.get("update_time"))
        )
        device = self._device
        if device is None or not self._is_current(observation, device):
            return
        if self._door_push is not None and not observation.is_newer(
            self._door_push.received_ns, self._door_push.update_time
        ):
            return
        self._door_push = observation
        self.async_write_ha_state()
