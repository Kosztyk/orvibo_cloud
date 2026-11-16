"""Test door observations through the door entity's push and poll callbacks."""

from importlib import import_module
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_ac import PACKAGE, protocol
from test_ls175_beta import FakeDeviceEntity


class BinarySensorEntity:
    pass


class DoorDeviceEntity(FakeDeviceEntity):
    def async_on_remove(self, remove_callback):
        pass

    def _handle_coordinator_update(self):
        self.async_write_ha_state()


dispatcher_connect = Mock()
with patch.dict(sys.modules, {
    "homeassistant": ModuleType("homeassistant"),
    "homeassistant.components.binary_sensor": SimpleNamespace(
        BinarySensorEntity=BinarySensorEntity,
        BinarySensorDeviceClass=SimpleNamespace(DOOR="door", CONNECTIVITY="connectivity"),
    ),
    "homeassistant.config_entries": SimpleNamespace(ConfigEntry=object),
    "homeassistant.core": SimpleNamespace(HomeAssistant=object, callback=lambda func: func),
    "homeassistant.helpers.dispatcher": SimpleNamespace(async_dispatcher_connect=dispatcher_connect),
    "homeassistant.helpers.entity": SimpleNamespace(EntityCategory=SimpleNamespace(DIAGNOSTIC="diagnostic")),
    "homeassistant.helpers.entity_platform": SimpleNamespace(AddEntitiesCallback=object),
    f"{PACKAGE}.const": SimpleNamespace(CONF_USER_ID="user_id", DOMAIN="orvibo_cloud"),
    f"{PACKAGE}.coordinator": SimpleNamespace(OrviboCloudCoordinator=object),
    f"{PACKAGE}.entity": SimpleNamespace(
        OrviboCloudDeviceEntity=DoorDeviceEntity, OrviboCloudEntity=DoorDeviceEntity,
    ),
}):
    binary_sensor = import_module(f"{PACKAGE}.binary_sensor")


class DoorFreshnessTests(unittest.TestCase):
    def setUp(self):
        dispatcher_connect.reset_mock()
        self.coordinator = SimpleNamespace(
            hass=object(), data=self.snapshot("closed", started=100),
            door_status_signal="orvibo_entry_door_status", last_push_reconnect_ns=0,
        )
        self.door = binary_sensor.OrviboDoorBinarySensor(self.coordinator, "door")
        self.push_callback = dispatcher_connect.call_args.args[-1]

    @staticmethod
    def snapshot(state, *, started, updated=None):
        # The vendor's status-only lock rows also work without a device array.
        devices = protocol.parse_readtable_devices({
            "data": {"deviceStatus": [{
                "deviceId": "door", "uid": "hardware",
                "properties": {"door_status": state}, "updateTimeSec": updated,
            }]},
        })
        return SimpleNamespace(devices=devices, device_snapshot_started_ns=started)

    def push(self, state, *, received, updated=None, device_id="door"):
        self.push_callback(
            {"device_id": device_id, "door_state": state, "update_time": updated},
            received,
        )

    def refresh(self, state, *, started, updated=None):
        self.coordinator.data = self.snapshot(state, started=started, updated=updated)
        self.door._handle_coordinator_update()

    def test_newer_poll_replaces_cached_push_and_the_next_push_is_accepted(self):
        self.assertIs(self.door.is_on, False)
        self.push("open", received=120)
        self.assertIs(self.door.is_on, True)
        self.refresh("closed", started=140)
        self.assertIs(self.door.is_on, False)
        self.push("open", received=120)
        self.assertIs(self.door.is_on, False)
        self.push("open", received=160)
        self.assertIs(self.door.is_on, True)

    def test_push_received_during_poll_is_newer_when_vendor_times_are_absent(self):
        self.push("open", received=150)
        self.refresh("closed", started=125)
        self.assertIs(self.door.is_on, True)

    def test_vendor_time_rejects_delayed_push_and_stale_poll(self):
        self.refresh("closed", started=120, updated=300)
        self.push("open", received=140, updated=299)
        self.assertIs(self.door.is_on, False)
        self.push("open", received=160, updated=310)
        self.refresh("closed", started=180, updated=301)
        self.assertIs(self.door.is_on, True)
        self.push("closed", received=190, updated=309)
        self.assertIs(self.door.is_on, True)
        self.refresh("closed", started=200, updated=320)
        self.assertIs(self.door.is_on, False)

    def test_reconnect_drops_previous_stream_and_keeps_fresh_events(self):
        self.push("open", received=120, updated=300)
        self.assertIs(self.door.is_on, True)
        self.coordinator.last_push_reconnect_ns = 150
        self.door._handle_coordinator_update()
        self.assertIs(self.door.is_on, False)
        self.push("open", received=140, updated=300)
        self.assertIs(self.door.is_on, False)
        self.push("open", received=160, updated=301, device_id="other-door")
        self.assertIs(self.door.is_on, False)
        self.push("open", received=170, updated=302)
        self.assertIs(self.door.is_on, True)
