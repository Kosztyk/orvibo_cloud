"""Exercise RF blind command history through the cover platform."""

from datetime import UTC, datetime
from enum import IntFlag
from importlib import import_module
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_ac import PACKAGE, HomeAssistantError, binary_fake, devices


class CoverFeatures(IntFlag):
    OPEN = 1
    CLOSE = 2
    SET_POSITION = 4
    STOP = 8


class CoverEntity:
    pass


class RestoreEntity:
    pass


class CoordinatorEntity:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self.async_write_ha_state = Mock()


registry = SimpleNamespace(
    DeviceInfo=SimpleNamespace, async_get_device_id_by_identifier=Mock(return_value=None)
)
with patch.dict(sys.modules, {
    "homeassistant": ModuleType("homeassistant"),
    "homeassistant.components.cover": SimpleNamespace(
        ATTR_POSITION="position", CoverDeviceClass=SimpleNamespace(CURTAIN="curtain"),
        CoverEntity=CoverEntity, CoverEntityFeature=CoverFeatures,
    ),
    "homeassistant.config_entries": SimpleNamespace(ConfigEntry=object),
    "homeassistant.const": SimpleNamespace(
        ATTR_ENTITY_ID="entity_id", ATTR_NAME="name", EVENT_LOGBOOK_ENTRY="logbook_entry"
    ),
    "homeassistant.core": SimpleNamespace(HomeAssistant=object, callback=lambda func: func),
    "homeassistant.exceptions": SimpleNamespace(HomeAssistantError=HomeAssistantError),
    "homeassistant.helpers": SimpleNamespace(device_registry=registry),
    "homeassistant.helpers.device_registry": registry,
    "homeassistant.helpers.entity_platform": SimpleNamespace(AddEntitiesCallback=object),
    "homeassistant.helpers.event": SimpleNamespace(async_track_point_in_utc_time=Mock()),
    "homeassistant.helpers.restore_state": SimpleNamespace(RestoreEntity=RestoreEntity),
    "homeassistant.helpers.update_coordinator": SimpleNamespace(CoordinatorEntity=CoordinatorEntity),
    "homeassistant.util": SimpleNamespace(dt=SimpleNamespace(utcnow=lambda: datetime.now(UTC))),
    f"{PACKAGE}.binary": binary_fake,
    f"{PACKAGE}.const": SimpleNamespace(
        CONF_FAMILY_ID="family_id", CONF_HOST="host", CONF_USER_ID="user_id", DOMAIN="orvibo_cloud"
    ),
    f"{PACKAGE}.coordinator": SimpleNamespace(OrviboCloudCoordinator=object),
}):
    cover = import_module(f"{PACKAGE}.cover")


class BlindActivityTests(unittest.IsolatedAsyncioTestCase):
    def blind(self, *, remember=True):
        discovered = devices(
            {"deviceId": "blind", "uid": "hub-uid", "deviceType": 34},
            {"deviceId": "hub", "uid": "hub-uid", "deviceType": 67},
        )
        hass = SimpleNamespace(
            async_add_executor_job=AsyncMock(return_value=(None, None, None, None)),
            bus=SimpleNamespace(async_fire=Mock()),
            states={"cover.test_blind": SimpleNamespace(name="Test blind")},
        )
        coordinator = SimpleNamespace(
            hass=hass,
            data=SimpleNamespace(devices=discovered, binary_user_name="test", binary_password="test"),
            entry=SimpleNamespace(
                entry_id="entry",
                data={"host": "homemate.orvibo.com", "family_id": "test", "user_id": "test"},
                options={"rf_blind_options": {"blind": {"remember_assumed_state": remember}}},
            ),
        )
        blind = cover.OrviboCurtainCover(coordinator, "blind")
        blind.entity_id = "cover.test_blind"
        blind._context = object()
        return blind

    def assert_stopped_entry(self, blind):
        blind.hass.bus.async_fire.assert_called_once_with(
            "logbook_entry",
            {"name": "Test blind", "entity_id": "cover.test_blind", "message": "Stopped"},
            context=blind._context,
        )

    async def test_stop_logs_the_action_without_inventing_position(self):
        blind = self.blind()
        await blind.async_close_cover()
        self.assertIs(blind.is_closed, True)
        blind.hass.bus.async_fire.assert_not_called()

        await blind.async_stop_cover()
        self.assertEqual(blind.hass.async_add_executor_job.await_args.args[7:9], ("rf control", 380002))
        self.assertEqual(blind.extra_state_attributes["last_action"], "stop")
        self.assertIsNone(blind.is_closed)
        self.assertIsNone(blind.current_cover_position)
        self.assert_stopped_entry(blind)

    async def test_stop_logs_even_without_remembering_assumed_state(self):
        blind = self.blind(remember=False)
        await blind.async_stop_cover()
        self.assertIsNone(blind.extra_state_attributes)
        self.assert_stopped_entry(blind)

    async def test_rejected_stop_does_not_log_a_successful_action(self):
        blind = self.blind()
        await blind.async_open_cover()
        blind.hass.async_add_executor_job.side_effect = ConnectionError("test failure")
        with self.assertRaises(HomeAssistantError):
            await blind.async_stop_cover()
        self.assertEqual(blind.extra_state_attributes["last_action"], "open")
        self.assertIs(blind.is_closed, False)
        blind.hass.bus.async_fire.assert_not_called()
