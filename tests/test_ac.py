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

    def test_baxi_all_four_swing_modes_generate_distinct_frames(self):
        p = profiles.IR_PROFILES[("5", "2", "7404")]
        self.assertEqual(p.swings, ("off", "vertical", "horizontal", "both"))
        signals = {}
        for mode in p.swings:
            with self.subTest(swing=mode):
                command = p.command(profiles.ACState(
                    mode="cool", temperature=19, fan="low", swing=mode,
                ))
                self.assertEqual(command.order, "ir control")
                self.assertEqual(command.infrared.frequency, 38000)
                self.assertEqual(len(command.infrared.pulses), 212)
                signals[mode] = command.infrared.pulses
        self.assertEqual(len(set(signals.values())), 4)
        # Horizontal-only must differ from BOTH and OFF, not silently alias.
        self.assertNotEqual(signals["horizontal"], signals["both"])
        self.assertNotEqual(signals["horizontal"], signals["off"])
        self.assertNotEqual(signals["vertical"], signals["both"])

    @staticmethod
    def _baxi_frame_from_pulses(pulses):
        """Decode LSB-first timing independently of the production encoder."""
        assert len(pulses) == 212
        assert tuple(pulses[:2]) == (9000, 4500)
        assert tuple(pulses[-2:]) == (560, 1000)
        frame = bytearray()
        for start in range(2, 210, 16):
            byte = 0
            for bit in range(8):
                mark, space = pulses[start + bit * 2:start + bit * 2 + 2]
                assert mark == 560
                assert space in (560, 1680)
                byte |= (space == 1680) << bit
            frame.append(byte)
        assert len(frame) == 13
        return bytes(frame)

    def test_baxi_16_to_32_entire_command_matrix(self):
        """408 full-state vectors: 2 HVAC * 17 temperatures * 3 fans * 4 swings."""
        p = profiles.IR_PROFILES[("5", "2", "7404")]
        self.assertEqual((min(p.temperatures), max(p.temperatures)), (16, 32))
        self.assertEqual(len(p.temperatures), 17)
        self.assertEqual(p.modes, ("off", "heat", "cool"))
        self.assertEqual(p.swings, ("off", "vertical", "horizontal", "both"))
        count = 0
        for mode in ("heat", "cool"):
            for fan in ("low", "medium", "high"):
                for swing in p.swings:
                    frames = set()
                    for temperature in range(16, 33):
                        with self.subTest(mode=mode, temp=temperature, fan=fan, swing=swing):
                            command = p.command(profiles.ACState(
                                mode=mode, temperature=temperature,
                                fan=fan, swing=swing, preset="none",
                            ))
                            self.assertEqual(command.infrared.frequency, 38000)
                            self.assertEqual(len(command.infrared.pulses), 212)
                            frame = self._baxi_frame_from_pulses(command.infrared.pulses)
                            self.assertEqual(frame[0], 0xC3)
                            self.assertEqual(frame[1] >> 3, temperature - 8)
                            self.assertEqual(frame[1] & 7, 0 if swing in ("vertical", "both") else 7)
                            self.assertEqual(bool(frame[2] & 0xE0), swing not in ("horizontal", "both"))
                            self.assertEqual(frame[12], sum(frame[:12]) & 255)
                            self.assertEqual(command.order, "ir control")
                            self.assertEqual(command.value1, 2 if mode == "heat" else 0)
                            self.assertEqual(command.value3 & 255, ("low", "medium", "high").index(fan) + 1)
                            self.assertEqual(command.value4, (temperature << 16) | (136 << 8))
                            frames.add(frame)
                            count += 1
                    self.assertEqual(len(frames), 17)
        self.assertEqual(count, 408)

    def test_baxi_previously_confirmed_commands_unchanged(self):
        known = {
            ("heat", 22, "low", "off"): "894d13318cf71f98e29ee97d6d7c0a64d8d41fe8406a3a774d5aa5e6036d6cd4",
            ("cool", 19, "low", "off"): "466ce8401f47e5b7d1e3f961e3c36df707e18b3da6e624d106e6dd60ba89ee34",
            ("heat", 23, "high", "both"): "2d090b302cec710ab4ec0dfae18831bc67258a698023cd0fbbe2b087e5fbb9a1",
            ("cool", 23, "medium", "horizontal"): "1db796b140d0171b5788c84de420762517792e1f44f1068f8d0c20bd4e92296a",
        }
        for (mode, temperature, fan, swing), fingerprint in known.items():
            with self.subTest(mode=mode, temperature=temperature, fan=fan, swing=swing):
                c = profiles.baxi_7404_candidate(
                    mode, temperature, fan,
                    vertical_swing=swing in ("vertical", "both"),
                    horizontal_swing=swing in ("horizontal", "both"),
                )
                actual = hashlib.sha256(",".join(map(str, c.infrared.pulses)).encode()).hexdigest()
                self.assertEqual(actual, fingerprint)

    def test_baxi_rejects_out_of_range_and_invalid_temperature_types(self):
        p = profiles.IR_PROFILES[("5", "2", "7404")]
        for mode in ("heat", "cool"):
            for invalid in (15, 33, 0, 39, True, False, 21.0, 22.5, "24"):
                with self.subTest(mode=mode, invalid=invalid):
                    with self.assertRaises(ValueError):
                        p.command(profiles.ACState(mode=mode, temperature=invalid))
                    with self.assertRaises(ValueError):
                        profiles.baxi_7404_candidate(mode, invalid, "low")

    def test_invalid_controls_fail(self):
        p=profiles.IR_PROFILES[("5","2","7404")]
        for state in (profiles.ACState(mode="fan_only"),
                      profiles.ACState(mode="cool",temperature=33),
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

    async def test_baxi_exposes_horizontal_swing_without_extra_commands(self):
        d=replace(self.d,ir_profile_id="7404",online=True)
        h=replace(self.h,device_type="30",online=True)
        self.coord.data.devices=(d,h)
        entities=[]
        await climate.async_setup_entry(self.hass,self.entry,entities.extend)
        entity,=entities
        self.assertEqual(entity._attr_swing_modes, ["off", "vertical", "horizontal", "both"])
        self.send.assert_not_awaited()  # No IR during discovery/setup.
        await entity.async_turn_on()
        self.assertEqual(self.send.await_count,1)
        await entity.async_set_swing_mode("horizontal")
        self.assertEqual(entity.swing_mode,"horizontal")
        self.assertEqual(self.send.await_count,2)  # Exactly one new IR request.
        self.assertEqual(self.send.await_args.args[-1].frequency, 38000)
        self.assertEqual(len(self.send.await_args.args[-1].pulses),212)
        await entity.async_set_swing_mode("both")
        self.assertEqual(entity.swing_mode,"both")
        self.assertEqual(self.send.await_count,3)

    async def test_baxi_ha_exposes_and_dispatches_extended_temperature(self):
        d = replace(self.d, ir_profile_id="7404", online=True)
        h = replace(self.h, device_type="30", online=True)
        self.coord.data.devices = (d, h)
        entities = []
        await climate.async_setup_entry(self.hass, self.entry, entities.extend)
        entity, = entities
        self.assertEqual((entity._attr_min_temp, entity._attr_max_temp), (16, 32))
        self.send.assert_not_awaited()
        for mode in (HVACMode.HEAT, HVACMode.COOL):
            await entity.async_set_hvac_mode(mode)
            for setpoint in (16, 32):
                with self.subTest(mode=mode, setpoint=setpoint):
                    await entity.async_set_temperature(temperature=setpoint)
                    sent = self.send.await_args.args[-1]
                    self.assertEqual(entity.native_target_temperature, setpoint)
                    self.assertEqual(entity.hvac_mode, mode)
                    self.assertEqual(len(sent.pulses), 212)
                    frame = ProtocolTests._baxi_frame_from_pulses(sent.pulses)
                    self.assertEqual(frame[1] >> 3, setpoint - 8)
        self.assertEqual(self.send.await_count, 6)

    async def test_baxi_ha_rejects_invalid_temperature_before_sending(self):
        d = replace(self.d, ir_profile_id="7404", online=True)
        h = replace(self.h, device_type="30", online=True)
        self.coord.data.devices = (d, h)
        entities = []
        await climate.async_setup_entry(self.hass, self.entry, entities.extend)
        entity, = entities
        await entity.async_turn_on()
        self.assertEqual(self.send.await_count, 1)
        for value in (15, 33, 22.5, True, None):
            with self.subTest(value=value), self.assertRaises(HomeAssistantError):
                await entity.async_set_temperature(temperature=value)
            self.assertEqual(self.send.await_count, 1)
            self.assertEqual(entity.native_target_temperature, 22)

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
