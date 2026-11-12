"""Offline regression tests for the AC profile and Home Assistant command path."""

import asyncio
from dataclasses import replace
from enum import IntFlag, StrEnum
import hashlib
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


PACKAGE = "_orvibo_ac_tests"
package = ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components/orvibo_cloud")
]
sys.modules[PACKAGE] = package
protocol = importlib.import_module(f"{PACKAGE}.protocol")
profiles = importlib.import_module(f"{PACKAGE}.ac_profiles")
binary = importlib.import_module(f"{PACKAGE}.binary")


class HVACMode(StrEnum):
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    AUTO = "auto"
    DRY = "dry"
    FAN_ONLY = "fan_only"


class Features(IntFlag):
    TARGET_TEMPERATURE = 1
    FAN_MODE = 8
    SWING_MODE = 32
    PRESET_MODE = 16
    TURN_OFF = 128
    TURN_ON = 256


class HomeAssistantError(Exception):
    pass


class DeviceEntity:
    def __init__(self, coordinator, device_id):
        self.coordinator = coordinator
        self._device_id = device_id
        self.async_write_ha_state = Mock()

    @property
    def _device(self):
        return next(
            (d for d in self.coordinator.data.devices if d.uid == self._device_id), None
        )

    @property
    def available(self):
        return self.coordinator.last_update_success


with patch.dict(sys.modules, {
    "homeassistant": ModuleType("homeassistant"),
    "homeassistant.components.climate": SimpleNamespace(
        ClimateEntity=object, ClimateEntityFeature=Features, HVACMode=HVACMode
    ),
    "homeassistant.config_entries": SimpleNamespace(ConfigEntry=object),
    "homeassistant.const": SimpleNamespace(UnitOfTemperature=SimpleNamespace(CELSIUS="°C")),
    "homeassistant.core": SimpleNamespace(HomeAssistant=object),
    "homeassistant.exceptions": SimpleNamespace(HomeAssistantError=HomeAssistantError),
    "homeassistant.helpers.entity_platform": SimpleNamespace(AddEntitiesCallback=object),
    f"{PACKAGE}.const": SimpleNamespace(
        DOMAIN="orvibo_cloud", CONF_FAMILY_ID="family_id", CONF_HOST="host"
    ),
    f"{PACKAGE}.coordinator": SimpleNamespace(OrviboCloudCoordinator=object),
    f"{PACKAGE}.entity": SimpleNamespace(OrviboCloudDeviceEntity=DeviceEntity),
}):
    climate = importlib.import_module(f"{PACKAGE}.climate")


AC_ROW = {
    "deviceId": "virtual-ac",
    "uid": "hardware",
    "model": "hub-model",
    "deviceType": 5,
    "subDeviceType": 2,
    "irDeviceId": 10502,
}
HUB_ROW = {
    "deviceId": "hub", "uid": "hardware", "model": "hub-model", "deviceType": 67
}


def devices(*rows):
    return protocol.parse_readtable_devices({"data": {"device": list(rows)}})


class ProfileTests(unittest.TestCase):
    def test_exact_match_and_invalid_profile_values(self):
        for value in (None, True, 10502.0, "10502x", "１０５０２", "0", 9999):
            with self.subTest(value=value):
                device, = devices({**AC_ROW, "irDeviceId": value})
                self.assertIsNone(profiles.ac_profile(device))
        for changes in (
            {"subDeviceType": 9},
            {"deviceType": 6},
            {"irDeviceID": 7404},
        ):
            with self.subTest(changes=changes):
                device, = devices({**AC_ROW, **changes})
                self.assertIsNone(profiles.ac_profile(device))
        row = {**AC_ROW, "irDeviceID": "10502"}
        row.pop("irDeviceId")
        device, = devices(row)
        self.assertEqual(profiles.ac_profile(device).manufacturer, "Daikin")

    def test_hub_diagnostics_distinguish_two_cubes_of_the_same_model(self):
        remote, matched, other = devices(
            {**AC_ROW, "deviceId": "ac", "irDeviceId": 7404, "parentUid": "cube-a"},
            {**HUB_ROW, "deviceId": "cube-a", "deviceType": 30},
            {**HUB_ROW, "deviceId": "cube-b", "deviceType": 30, "uid": "other"},
        )
        self.assertEqual(protocol.ac_hub_matches(remote, (matched, other)), [
            {
                "device_type": "30", "same_model": True, "same_cloud_uid": True,
                "parent_match": True, "online": None,
            },
            {
                "device_type": "30", "same_model": True, "same_cloud_uid": False,
                "parent_match": False, "online": None,
            },
        ])

    def test_baxi_candidate_reproduces_the_confirmed_baseline(self):
        device, = devices({**AC_ROW, "irDeviceId": 7404})
        profile = profiles.ac_profile(device)
        baseline = profile.command(profiles.ACState(mode="heat"))
        self.assertEqual(profiles.baxi_7404_candidate("heat", 22, "low"), baseline)
        candidate = profiles.baxi_7404_candidate("cool", 24, "low")
        self.assertEqual(candidate.value2, 211124)
        self.assertEqual(candidate.value4 >> 16, 24)
        self.assertNotEqual(candidate.infrared.pulses, baseline.infrared.pulses)
        verified_cool = profile.command(profiles.ACState(mode="cool"))
        self.assertEqual(verified_cool, profiles.baxi_7404_candidate("cool", 19, "low"))
        self.assertEqual(verified_cool.value4 >> 16, 19)
        self.assertNotEqual(verified_cool, candidate)

    def test_verified_off_frame_and_wire_format(self):
        device, = devices(AC_ROW)
        profile = profiles.ac_profile(device)
        signal = profile.command(profiles.ACState(mode="off")).infrared
        payload = binary.OrviboBinaryClient("test.invalid", "test", "test", "family")
        packet = payload._control_payload(
            device.uid, device.cloud_uid, "ir control", 0, 0, 0, 0, infrared=signal
        )
        self.assertEqual(packet["freq"], 38000)
        self.assertEqual(packet["pluseNum"], 584)
        self.assertEqual(
            hashlib.sha256(packet["pluseData"].encode()).hexdigest(),
            "584c9f76d0aea0da52e97435daaa1cacc41642f26fdf5b04b3fd8d4e1a7e6b0e",
        )
        self.assertEqual(packet["deviceId"], "virtual-ac")
        self.assertEqual(packet["uid"], "hardware")
        for state in (
            profiles.ACState(mode="invalid"),
            profiles.ACState(mode="off", temperature=31),
            profiles.ACState(mode="off", fan="turbo"),
        ):
            with self.subTest(state=state), self.assertRaises(ValueError):
                profile.command(state)


class ClimateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hub, self.child = devices(AC_ROW, HUB_ROW)
        self.send = AsyncMock()
        self.entry = SimpleNamespace(
            entry_id="entry",
            data={"host": "test.invalid", "family_id": "family"},
            options={"selected_device_ids": ["virtual-ac"]},
        )
        self.coordinator = SimpleNamespace(
            entry=self.entry,
            data=SimpleNamespace(
                devices=(self.child, self.hub),
                binary_user_name="test-user",
                binary_password="test-password",
            ),
            last_update_success=True,
            hass=SimpleNamespace(async_add_executor_job=self.send),
            tv_control_lock=asyncio.Lock(),
        )
        self.hass = SimpleNamespace(data={"orvibo_cloud": {"entry": self.coordinator}})
        entities = []
        await climate.async_setup_entry(self.hass, self.entry, entities.extend)
        self.entity, = entities

    async def test_setup_and_explicit_off(self):
        self.send.assert_not_awaited()
        self.assertIsNone(self.entity.hvac_mode)
        self.assertTrue(self.entity.available)
        self.assertTrue(self.entity._attr_supported_features & Features.TURN_OFF)
        await self.entity.async_turn_off()
        self.send.assert_awaited_once()
        args = self.send.await_args.args
        self.assertEqual(args[5:8], ("virtual-ac", "hardware", "ir control"))
        self.assertEqual(len(args[-1].pulses), 584)
        self.assertEqual(self.entity.hvac_mode, HVACMode.OFF)
        self.entity.async_write_ha_state.assert_called_once()

    async def test_baxi_off_uses_virtual_remote_and_scene_signal(self):
        child = replace(self.child, ir_profile_id="7404", online=True)
        hub = replace(self.hub, device_type="30", online=True)
        self.coordinator.data.devices = (child, hub, replace(hub, uid="second-row"))
        entities = []
        await climate.async_setup_entry(self.hass, self.entry, entities.extend)
        entity, = entities
        self.assertTrue(entity.available)
        await entity.async_turn_off()
        self.send.assert_awaited_once()
        args = self.send.await_args.args
        self.assertEqual(args[5:8], ("virtual-ac", "hardware", "ir control"))
        self.assertEqual(args[8:12], (3, 141122, 257, 1476608))
        self.assertEqual(args[-1].frequency, 38000)
        self.assertEqual(len(args[-1].pulses), 212)
        self.assertEqual(
            hashlib.sha256(",".join(map(str, args[-1].pulses)).encode()).hexdigest(),
            "c3c544748ab3f2c89180f701299d920e51c61cc216c380c77e162f1499f87eae",
        )
        self.assertEqual(entity.hvac_mode, HVACMode.OFF)
        self.coordinator.data.devices = (child, replace(hub, cloud_uid="unrelated"))
        self.assertFalse(entity.available)

    async def test_baxi_on_and_follow_up_settings_preserve_requested_state(self):
        child = replace(self.child, ir_profile_id="7404", online=True)
        hub = replace(self.hub, device_type="30", online=True)
        self.coordinator.data.devices = (child, hub)
        entities = []
        await climate.async_setup_entry(self.hass, self.entry, entities.extend)
        entity, = entities
        self.assertEqual(
            entity._attr_supported_features,
            Features.TURN_ON | Features.TURN_OFF | Features.TARGET_TEMPERATURE
            | Features.FAN_MODE | Features.SWING_MODE | Features.PRESET_MODE,
        )
        await entity.async_turn_on()
        self.assertEqual(entity.hvac_mode, HVACMode.HEAT)
        args = self.send.await_args.args
        self.assertEqual(args[8:12], (2, 241122, 257, 1476608))
        self.assertEqual(args[-1].frequency, 38000)
        self.assertEqual(len(args[-1].pulses), 212)
        self.assertEqual(
            hashlib.sha256(",".join(map(str, args[-1].pulses)).encode()).hexdigest(),
            "894d13318cf71f98e29ee97d6d7c0a64d8d41fe8406a3a774d5aa5e6036d6cd4",
        )
        await entity.async_set_hvac_mode(HVACMode.COOL)
        await entity.async_set_temperature(temperature=23)
        await entity.async_set_fan_mode("medium")
        await entity.async_set_swing_mode("both")
        args = self.send.await_args.args
        expected = profiles.baxi_7404_candidate(
            "cool", 23, "medium", vertical_swing=True, horizontal_swing=True
        )
        self.assertEqual(args[-1], expected.infrared)
        self.assertEqual(entity.target_temperature, 23)
        self.assertEqual(entity.fan_mode, "medium")
        self.assertEqual(entity.swing_mode, "both")
        with self.assertRaises(HomeAssistantError):
            await entity.async_set_temperature(temperature=24)
        with self.assertRaises(HomeAssistantError):
            await entity.async_set_fan_mode("auto")
        await entity.async_set_swing_mode("horizontal")
        horizontal = profiles.baxi_7404_candidate("cool", 23, "medium", horizontal_swing=True)
        self.assertEqual(self.send.await_args.args[-1], horizontal.infrared)
        self.assertEqual(entity.swing_mode, "horizontal")
        self.assertEqual(self.send.await_count, 6)
        await entity.async_turn_off()
        self.assertEqual(entity.hvac_mode, HVACMode.OFF)
        self.assertEqual(self.send.await_args.args[8:12], (3, 141122, 257, 1476608))

    async def test_baxi_experimental_presets_and_momentary_display(self):
        child = replace(self.child, ir_profile_id="7404", online=True)
        hub = replace(self.hub, device_type="30", online=True)
        self.coordinator.data.devices = (child, hub)
        entities = []
        await climate.async_setup_entry(self.hass, self.entry, entities.extend)
        entity, = entities
        await entity.async_set_hvac_mode(HVACMode.COOL)
        await entity.async_set_preset_mode("turbo")
        turbo = profiles.baxi_7404_candidate("cool", 19, "low", trial_extra="turbo")
        self.assertEqual(self.send.await_args.args[-1], turbo.infrared)
        self.assertEqual(entity.preset_mode, "turbo")
        await entity.async_set_preset_mode("display")
        display = profiles.baxi_7404_candidate("cool", 19, "low", trial_extra="display")
        self.assertEqual(self.send.await_args.args[-1], display.infrared)
        self.assertEqual(entity.preset_mode, "none")
        await entity.async_set_temperature(temperature=23)
        baseline = profiles.baxi_7404_candidate("cool", 23, "low")
        self.assertEqual(self.send.await_args.args[-1], baseline.infrared)
        with self.assertRaises(HomeAssistantError):
            await entity.async_set_preset_mode("eco")
        self.assertEqual(self.send.await_count, 4)

    async def test_unselected_and_unknown_remotes_are_skipped(self):
        for options, discovered in (
            ({"selected_device_ids": ["hub"]}, (self.child, self.hub)),
            (self.entry.options, devices({**AC_ROW, "irDeviceId": 9999}, HUB_ROW)),
        ):
            self.entry.options = options
            self.coordinator.data.devices = discovered
            entities = []
            await climate.async_setup_entry(self.hass, self.entry, entities.extend)
            self.assertEqual(entities, [])

    async def test_invalid_controls_never_send(self):
        with self.assertRaises(HomeAssistantError):
            await self.entity.async_set_hvac_mode("invalid")
        with self.assertRaises(HomeAssistantError):
            await self.entity.async_set_temperature(temperature=31)
        with self.assertRaises(HomeAssistantError):
            await self.entity.async_set_fan_mode("turbo")
        self.send.assert_not_awaited()

    async def test_daikin_preserves_v06_settings_and_off_frame(self):
        await self.entity.async_set_temperature(temperature=21)
        await self.entity.async_set_fan_mode("medium")
        self.assertEqual(self.entity._attr_swing_modes, ["off", "vertical"])
        for mode in ("horizontal", "both"):
            with self.assertRaises(HomeAssistantError):
                await self.entity.async_set_swing_mode(mode)
        await self.entity.async_set_swing_mode("vertical")
        await self.entity.async_set_preset_mode("eco_comfort")
        self.send.assert_not_awaited()
        await self.entity.async_set_hvac_mode(HVACMode.COOL)
        for powered in (True, False, True):
            if not powered:
                await self.entity.async_turn_off()
            elif self.entity.hvac_mode == HVACMode.OFF:
                await self.entity.async_turn_on()
            expected = profiles.daikin_signal(
                power=powered, mode="cool", temperature=21, fan="medium",
                eco=True, comfort=True, swing_v=True, swing_h=False,
            )
            self.assertEqual(self.send.await_args.args[-1].pulses, expected.pulses)
        self.assertEqual(self.entity.hvac_mode, HVACMode.COOL)
        self.assertEqual(self.send.await_count, 3)

    async def test_revalidates_device_and_hub_before_sending(self):
        for discovered in (
            (self.child,),
            (self.child, replace(self.hub, online=False)),
            (self.child, replace(self.hub, model="different")),
            (self.child, self.hub, replace(self.hub, uid="other-hub")),
            (replace(self.child, ir_profile_id="7404"), self.hub),
        ):
            self.coordinator.data.devices = discovered
            with self.subTest(discovered=discovered):
                self.assertFalse(self.entity.available)
                with self.assertRaises(HomeAssistantError):
                    await self.entity.async_turn_off()
        self.send.assert_not_awaited()

    async def test_failed_acknowledgement_preserves_unknown_state(self):
        self.send.side_effect = binary.OrviboBinaryError("private data")
        with self.assertRaisesRegex(HomeAssistantError, "did not acknowledge"):
            await self.entity.async_turn_off()
        self.send.assert_awaited_once()
        self.assertIsNone(self.entity.hvac_mode)
        self.entity.async_write_ha_state.assert_not_called()
