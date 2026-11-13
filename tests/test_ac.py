"""Offline IR/climate regression coverage without Home Assistant or cloud access."""
from __future__ import annotations

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

PACKAGE = "_orvibo_ac_beta_tests"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/orvibo_cloud")]
sys.modules[PACKAGE] = package
protocol = importlib.import_module(f"{PACKAGE}.protocol")
profiles = importlib.import_module(f"{PACKAGE}.ac_profiles")


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
    PRESET_MODE = 16
    SWING_MODE = 32
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
        return next((d for d in self.coordinator.data.devices if d.uid == self._device_id), None)

    @property
    def available(self):
        return self.coordinator.last_update_success and self._device is not None


class OrviboBinaryError(Exception):
    pass


binary_fake = ModuleType(f"{PACKAGE}.binary")
binary_fake.OrviboBinaryError = OrviboBinaryError
binary_fake.control_device = Mock()

with patch.dict(sys.modules, {
    "homeassistant": ModuleType("homeassistant"),
    "homeassistant.components": ModuleType("homeassistant.components"),
    "homeassistant.components.climate": SimpleNamespace(
        ClimateEntity=object, ClimateEntityFeature=Features, HVACMode=HVACMode,
    ),
    "homeassistant.config_entries": SimpleNamespace(ConfigEntry=object),
    "homeassistant.const": SimpleNamespace(UnitOfTemperature=SimpleNamespace(CELSIUS="°C")),
    "homeassistant.core": SimpleNamespace(HomeAssistant=object),
    "homeassistant.exceptions": SimpleNamespace(HomeAssistantError=HomeAssistantError),
    "homeassistant.helpers": ModuleType("homeassistant.helpers"),
    "homeassistant.helpers.entity_platform": SimpleNamespace(AddEntitiesCallback=object),
    f"{PACKAGE}.binary": binary_fake,
    f"{PACKAGE}.const": SimpleNamespace(
        DOMAIN="orvibo_cloud", CONF_FAMILY_ID="family_id", CONF_HOST="host"
    ),
    f"{PACKAGE}.coordinator": SimpleNamespace(OrviboCloudCoordinator=object),
    f"{PACKAGE}.entity": SimpleNamespace(OrviboCloudDeviceEntity=DeviceEntity),
}):
    climate = importlib.import_module(f"{PACKAGE}.climate")
    backend = importlib.import_module(f"{PACKAGE}.ac_backend")


AC_ROW = {
    "deviceId": "virtual-ac", "uid": "hardware", "model": "hub-model",
    "deviceType": 5, "subDeviceType": 2, "irDeviceId": 10502,
}
HUB_ROW = {
    "deviceId": "hub", "uid": "hardware", "model": "hub-model", "deviceType": 67,
}


def devices(*rows):
    return protocol.parse_readtable_devices({"data": {"device": list(rows)}})


class ProtocolTests(unittest.TestCase):
    def test_daikin_fingerprint(self):
        s = profiles.daikin_signal(power=False)
        self.assertEqual(len(s.pulses), 584)
        self.assertEqual(s.frequency, 38000)
        self.assertEqual(
            hashlib.sha256(",".join(map(str, s.pulses)).encode()).hexdigest(),
            profiles.daikin_signal.__globals__["OFF_23_HEAT_SHA256"],
        )

    def test_exact_matches(self):
        d, = devices(AC_ROW)
        self.assertEqual(profiles.ac_profile(d).manufacturer, "Daikin")
        d, = devices({**AC_ROW, "irDeviceId": 7404})
        self.assertEqual(profiles.ac_profile(d).manufacturer, "BAXI")

    def test_reject_invalid_ids_and_conflicts(self):
        for value in (None, True, 10502.0, "10502x", "１０５０２", "0", 9999):
            with self.subTest(value=value):
                d, = devices({**AC_ROW, "irDeviceId": value})
                self.assertIsNone(profiles.ac_profile(d))
        d, = devices({**AC_ROW, "irDeviceID": 7404})
        self.assertIsNone(profiles.ac_profile(d))

    def test_match_alias_and_subtype(self):
        d, = devices({**AC_ROW, "irDeviceId": "10502", "irDeviceID": "10502"})
        self.assertEqual(d.ir_profile_id, "10502")
        d, = devices({**AC_ROW, "subDeviceType": 9})
        self.assertIsNone(profiles.ac_profile(d))

    def test_hub_route_fails_closed(self):
        h, d = devices(AC_ROW, HUB_ROW)
        self.assertTrue(backend.has_available_route(d, (d,h), "67"))
        self.assertFalse(backend.has_available_route(d, (d,), "67"))
        self.assertFalse(backend.has_available_route(d, (d,h,replace(h,uid="dup")), "67"))
        self.assertFalse(backend.has_available_route(d, (d,replace(h,model="wrong")), "67"))

    def test_duplicate_magic_cube_route_allowed_if_online(self):
        h,d = devices({**AC_ROW,"irDeviceId":7404,"online":True}, {**HUB_ROW,"deviceType":30,"online":True})
        self.assertTrue(backend.has_available_route(d,(d,h,replace(h,uid="other")),"30"))
        self.assertFalse(backend.has_available_route(replace(d, online=False),(d,h),"30"))
        self.assertFalse(backend.has_available_route(d,(d,replace(h,online=False)),"30"))

    def test_baxi_off_reference(self):
        d, = devices({**AC_ROW,"irDeviceId":7404})
        cmd = profiles.ac_profile(d).command(profiles.ACState(mode="off"))
        self.assertEqual((cmd.order, cmd.value1, cmd.value2, cmd.value3, cmd.value4),
                         ("ir control", 3, 141122, 257, 1476608))
        self.assertEqual(len(cmd.infrared.pulses),212)
        self.assertEqual(cmd.infrared.frequency,38000)

    def test_baxi_encoded_frames(self):
        p = profiles.IR_PROFILES[("5","2","7404")]
        heat = p.command(profiles.ACState(mode="heat"))
        cool = p.command(profiles.ACState(mode="cool"))
        self.assertEqual(heat, profiles.baxi_7404_candidate("heat",22,"low"))
        self.assertEqual(cool, profiles.baxi_7404_candidate("cool",19,"low"))
        self.assertEqual(len(heat.infrared.pulses), 212)
        self.assertNotEqual(heat.infrared.pulses, cool.infrared.pulses)

    def test_no_horizontal_only_in_public_climate(self):
        p = profiles.IR_PROFILES[("5","2","7404")]
        self.assertNotIn("horizontal", p.swings)
        with self.assertRaisesRegex(ValueError,"swing"):
            p.command(profiles.ACState(mode="cool",temperature=19,fan="low",swing="horizontal"))
        self.assertIn("both",p.swings)

    def test_invalid_controls_fail(self):
        p=profiles.IR_PROFILES[("5","2","7404")]
        for state in (profiles.ACState(mode="fan_only"),
                      profiles.ACState(mode="cool",temperature=25),
                      profiles.ACState(mode="heat",fan="auto")):
            with self.subTest(state=state), self.assertRaises(ValueError):
                p.command(state)

    def test_diagnostic_hub_flags_hide_ids(self):
        h, d = devices(AC_ROW, HUB_ROW)
        vals=protocol.ac_hub_matches(d,(h,))
        self.assertEqual(len(vals),1)
        self.assertEqual(vals[0]["device_type"],"67")
        self.assertNotIn("uid",vals[0])
        self.assertTrue(vals[0]["same_cloud_uid"])


class ClimateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h, self.d = devices(AC_ROW,HUB_ROW)
        self.send=AsyncMock()
        self.entry=SimpleNamespace(entry_id="entry",data={"host":"test.invalid","family_id":"family"},
                                   options={"selected_device_ids":["virtual-ac"]})
        self.coord=SimpleNamespace(entry=self.entry,
            data=SimpleNamespace(devices=(self.d,self.h),binary_user_name="user",binary_password="password"),
            last_update_success=True,
            hass=SimpleNamespace(async_add_executor_job=self.send),
            tv_control_lock=asyncio.Lock(),
            vivax_scene_modes={}, vivax_scene_error=None)
        self.hass=SimpleNamespace(data={"orvibo_cloud":{"entry":self.coord}})
        entities=[]
        await climate.async_setup_entry(self.hass,self.entry,entities.extend)
        self.entity,=entities

    async def test_setup_never_sends(self):
        self.send.assert_not_awaited()
        self.assertIsNone(self.entity.hvac_mode)
        self.assertTrue(self.entity.available)

    async def test_daikin_off_with_correct_route(self):
        await self.entity.async_turn_off()
        self.send.assert_awaited_once()
        args=self.send.await_args.args
        self.assertEqual(args[5:8],("virtual-ac","hardware","ir control"))
        self.assertEqual(len(args[-1].pulses),584)
        self.assertEqual(self.entity.hvac_mode,HVACMode.OFF)

    async def test_daikin_local_off_settings_and_restore(self):
        await self.entity.async_set_temperature(temperature=21)
        await self.entity.async_set_fan_mode("medium")
        self.send.assert_not_awaited()
        await self.entity.async_set_hvac_mode(HVACMode.COOL)
        await self.entity.async_turn_off()
        await self.entity.async_turn_on()
        self.assertEqual(self.entity.hvac_mode,HVACMode.COOL)
        self.assertEqual(self.entity.native_target_temperature,21)
        self.assertEqual(self.send.await_count,3)

    async def test_baxi_on_and_off(self):
        d=replace(self.d,ir_profile_id="7404",online=True)
        h=replace(self.h,device_type="30",online=True)
        self.coord.data.devices=(d,h,replace(h,uid="second"))
        entities=[]
        await climate.async_setup_entry(self.hass,self.entry,entities.extend)
        entity,=entities
        await entity.async_turn_on()
        self.assertEqual((entity.hvac_mode,entity.native_target_temperature),(HVACMode.HEAT,22))
        await entity.async_turn_off()
        self.assertEqual(len(self.send.await_args.args[-1].pulses),212)
        self.assertEqual(self.send.await_count,2)

    async def test_baxi_rejects_unverified_swing(self):
        d=replace(self.d,ir_profile_id="7404",online=True)
        h=replace(self.h,device_type="30",online=True)
        self.coord.data.devices=(d,h)
        entities=[]
        await climate.async_setup_entry(self.hass,self.entry,entities.extend)
        entity,=entities
        self.assertNotIn("horizontal",entity._attr_swing_modes)
        await entity.async_turn_on()
        with self.assertRaises(HomeAssistantError):
            await entity.async_set_swing_mode("horizontal")
        self.assertEqual(self.send.await_count,1)

    async def test_failure_preserves_unknown_state(self):
        self.send.side_effect=OrviboBinaryError("private secret")
        with self.assertRaisesRegex(HomeAssistantError,"did not acknowledge"):
            await self.entity.async_turn_off()
        self.assertIsNone(self.entity.hvac_mode)
        self.entity.async_write_ha_state.assert_not_called()

    async def test_missing_hub_rejects_command(self):
        self.coord.data.devices=(self.d,)
        with self.assertRaisesRegex(HomeAssistantError,"unavailable"):
            await self.entity.async_turn_off()
        self.send.assert_not_awaited()

    async def test_unselected_remotes_skipped(self):
        self.entry.options={"selected_device_ids":["hub"]}
        entities=[]
        await climate.async_setup_entry(self.hass,self.entry,entities.extend)
        self.assertEqual(entities,[])

    async def test_invalid_temperature_never_sends(self):
        with self.assertRaises(HomeAssistantError):
            await self.entity.async_set_temperature(temperature=22.5)
        with self.assertRaises(HomeAssistantError):
            await self.entity.async_set_temperature(temperature=35)
        self.send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
