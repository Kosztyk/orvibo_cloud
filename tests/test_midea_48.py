"""Offline Midea 48-bit protocol and Vivax climate regression checks."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from test_ac import (
    PACKAGE, AC_ROW, HUB_ROW, HVACMode, HomeAssistantError,
    OrviboBinaryError, climate, devices, profiles,
)

midea = importlib.import_module(f"{PACKAGE}.midea_48")


class Midea48WireTests(unittest.TestCase):
    def test_reference_checksum_vectors(self):
        """Expected values from IRremoteESP8266 test/ir_Midea_test.cpp."""
        for frame, expected in [
            (0xA1826FFFFF62, 0x62),
            (0xA18177FFFF70, 0x70),
            (0xA1806FFFFF61, 0x61),
            (0x1234567890AB, 0xDF),
            (0x000000000000, 0x00),
            (0xFFFFFFFFFFFF, 0xA0),
        ]:
            with self.subTest(hex_frame=hex(frame)):
                self.assertEqual(midea.midea48_checksum(frame), expected)

    def test_state_power_temperature_mode_and_fan(self):
        values = set()
        for mode, raw_mode in midea.MIDEA_MODES.items():
            for fan, raw_fan in midea.MIDEA_FANS.items():
                for temp in range(17, 31):
                    frame = midea.midea48_state(power=True,mode=mode,temperature=temp,fan=fan)
                    data = frame.to_bytes(6,"big")
                    self.assertEqual(data[0], 0xA1)
                    self.assertEqual(data[1] & 0x80, 0x80)
                    self.assertEqual(data[1] & 0x7, raw_mode)
                    self.assertEqual((data[1] >> 3) & 0x3,raw_fan)
                    self.assertEqual(data[2], 0x40 | (temp-17))
                    self.assertEqual(data[3:5], b"\xff\xff")
                    self.assertEqual(data[-1], midea.midea48_checksum(frame))
                    values.add(frame)
        self.assertEqual(len(values),5*4*14)
        self.assertEqual(midea.midea48_state(power=True,mode="cool",temperature=23,fan="auto"),0xA18046FFFF58)
        self.assertEqual(midea.midea48_state(power=True,mode="heat",temperature=23,fan="auto"),0xA18346FFFF5A)
        self.assertEqual(midea.midea48_state(power=False,mode="cool",temperature=23,fan="auto"),0xA10046FFFFD8)
        # Two exact IRremoteESP8266 CelsiusRemoteTemp vectors (issue #819).
        self.assertEqual(midea.midea48_state(power=True,mode="cool",temperature=17,fan="low"),0xA18840FFFF56)
        self.assertEqual(midea.midea48_state(power=True,mode="cool",temperature=30,fan="low"),0xA1884DFFFF5D)

    def test_wire_frame_then_bitwise_inverse_msb_first(self):
        """Reference sends 48 bits MSB-first then all 48 complemented bits."""
        frame=0xA1826FFFFF62
        p=midea.midea48_pulses(frame)
        self.assertEqual(len(p),200)
        self.assertEqual(p[:2],(4480,4480))
        self.assertEqual(p[100:102],(4480,4480))
        self.assertEqual(p[98:100],(560,5600))
        self.assertEqual(p[-2:],(560,5600))
        def unpack(pulses):
            bits=[int(pulses[3 + 2*i] == 1680) for i in range(48)]
            return int(''.join(str(b) for b in bits),2)
        self.assertEqual(unpack(p[:100]),frame)
        self.assertEqual(unpack(p[100:]),frame^midea.MIDEA_MASK)

    def test_toggle_is_distinct_valid_midea_special_packet(self):
        sig=midea.midea48_swing_toggle_signal()
        self.assertEqual(sig.frame,0xA202FFFFFF7E)
        self.assertEqual(sig.frequency,38000)
        self.assertEqual(len(sig.pulses),200)
        self.assertEqual(midea.midea48_checksum(sig.frame),0x7e)
        # Only the command value changes; the 48-bit pulse encoder is shared.
        self.assertEqual(sig.pulses, midea.midea48_pulses(0xA202FFFFFF7E))
        self.assertNotEqual(sig.pulses, midea.midea48_pulses(0xA201FFFFFF7C))

    def test_reject_invalid_inputs(self):
        for x in (-1,2**48,True,'0'):
            with self.subTest(frame=x),self.assertRaises(ValueError):
                midea.midea48_pulses(x)
        for kwargs in (
            {'power':1,'mode':'cool','temperature':23,'fan':'auto'},
            {'power':True,'mode':'foo','temperature':23,'fan':'auto'},
            {'power':True,'mode':'cool','temperature':31,'fan':'auto'},
            {'power':True,'mode':'cool','temperature':16,'fan':'auto'},
            {'power':True,'mode':'cool','temperature':True,'fan':'auto'},
            {'power':True,'mode':'cool','temperature':23,'fan':'eco'},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                midea.midea48_state(**kwargs)

    def test_exact_registry_match_without_scenes(self):
        d,=devices({**AC_ROW,'irDeviceId':7579})
        p=profiles.ac_profile(d)
        self.assertEqual(p.manufacturer,'Vivax / Midea')
        self.assertEqual(p.temperatures,range(17,31))
        self.assertEqual(p.swings,('off','vertical'))
        self.assertEqual(p.hub_type,'67')
        self.assertIsNotNone(p.swing_toggle_encoder)
        for id in ('7578','75790','7404'):
            d,=devices({**AC_ROW,'irDeviceId':id})
            if id=='7404':
                self.assertEqual(profiles.ac_profile(d).manufacturer,'BAXI')
            else:
                self.assertIsNone(profiles.ac_profile(d))

    def test_off_and_on_are_distinct_200_pulse_commands(self):
        p=profiles.IR_PROFILES[('5','2','7579')]
        a=p.command(profiles.ACState(mode='off',previous_mode='cool',temperature=23,fan='auto'))
        b=p.command(profiles.ACState(mode='cool',temperature=23,fan='auto'))
        self.assertEqual(a.order,'ir control')
        self.assertEqual(len(a.infrared.pulses),200)
        self.assertEqual(a.infrared.frequency,38000)
        self.assertNotEqual(a.infrared.pulses,b.infrared.pulses)
        self.assertEqual((a.value1,a.value2,a.value3,a.value4),(0,0,0,0))


class MideaClimateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hub,self.vivax=devices({**AC_ROW,'irDeviceId':7579,'online':True},
                                    {**HUB_ROW,'online':True})
        self.send=AsyncMock()
        self.entry=SimpleNamespace(entry_id='entry',data={'host':'test.invalid','family_id':'family'},
                                   options={'selected_device_ids':['virtual-ac']})
        # No client and no scene fields. That ensures setup never reads scenes.
        self.coord=SimpleNamespace(entry=self.entry,
            data=SimpleNamespace(devices=(self.vivax,self.hub),binary_user_name='user',binary_password='password'),
            last_update_success=True,
            hass=SimpleNamespace(async_add_executor_job=self.send),
            tv_control_lock=asyncio.Lock())
        self.hass=SimpleNamespace(data={'orvibo_cloud':{'entry':self.coord}})
        entities=[]
        await climate.async_setup_entry(self.hass,self.entry,entities.extend)
        self.assertEqual(len(entities),1)
        self.entity=entities[0]

    async def test_setup_no_network_or_ir(self):
        self.send.assert_not_awaited()
        self.assertIsNone(self.entity.hvac_mode)
        self.assertEqual(self.entity._attr_min_temp,17)
        self.assertEqual(self.entity._attr_max_temp,30)
        self.assertEqual(self.entity._attr_unique_id,'virtual-ac_ir_climate')
        self.assertEqual(self.entity._attr_fan_modes,['auto','low','medium','high'])
        self.assertEqual(self.entity._attr_swing_modes,['off','vertical'])
        self.assertTrue(self.entity.available)

    async def test_modes_temperature_fan_and_off(self):
        await self.entity.async_set_hvac_mode(HVACMode.COOL)
        self.assertEqual(self.entity.hvac_mode,HVACMode.COOL)
        await self.entity.async_set_temperature(temperature=24)
        self.assertEqual(self.entity.native_target_temperature,24)
        await self.entity.async_set_fan_mode('high')
        self.assertEqual(self.entity.fan_mode,'high')
        await self.entity.async_set_hvac_mode(HVACMode.HEAT)
        await self.entity.async_turn_off()
        self.assertEqual(self.entity.hvac_mode,HVACMode.OFF)
        await self.entity.async_turn_on()
        self.assertEqual(self.entity.hvac_mode,HVACMode.HEAT)
        self.assertEqual(self.entity.native_target_temperature,24)
        self.assertEqual(self.send.await_count,6)
        self.assertEqual(len(self.send.await_args.args[-1].pulses),200)

    async def test_offline_temperature_and_fan_stored_locally(self):
        await self.entity.async_set_temperature(temperature=26)
        await self.entity.async_set_fan_mode('low')
        self.send.assert_not_awaited()
        await self.entity.async_turn_on()
        self.assertEqual(self.entity.native_target_temperature,26)
        self.assertEqual(self.entity.fan_mode,'low')
        self.send.assert_awaited_once()

    async def test_swing_is_only_a_toggle_and_does_not_send_full_state(self):
        await self.entity.async_set_hvac_mode(HVACMode.COOL)
        with self.assertRaisesRegex(HomeAssistantError,'unknown'):
            await self.entity.async_set_swing_mode('off')
        self.assertEqual(self.send.await_count,1)
        await self.entity.async_set_swing_mode('vertical')
        self.assertEqual(self.entity.swing_mode,'vertical')
        self.assertEqual(self.send.await_count,2)
        last=self.send.await_args.args[-1]
        self.assertEqual(last.pulses,midea.midea48_swing_toggle_signal().pulses)
        await self.entity.async_set_swing_mode('vertical')
        self.assertEqual(self.send.await_count,2) # idempotent at HA assumed-state level
        await self.entity.async_set_swing_mode('off')
        self.assertEqual(self.entity.swing_mode,'off')
        self.assertEqual(self.send.await_count,3)
        self.assertEqual(self.send.await_args.args[-1].pulses,last.pulses)

    async def test_swing_while_off_and_bad_modes_rejected(self):
        with self.assertRaisesRegex(HomeAssistantError,'Turn the AC on'):
            await self.entity.async_set_swing_mode('vertical')
        with self.assertRaises(HomeAssistantError):
            await self.entity.async_set_swing_mode('horizontal')
        self.send.assert_not_awaited()

    async def test_failed_ack_does_not_move_state(self):
        self.send.side_effect=OrviboBinaryError('do not show payload')
        with self.assertRaisesRegex(HomeAssistantError,'did not acknowledge'):
            await self.entity.async_turn_on()
        self.assertIsNone(self.entity.hvac_mode)
        self.assertEqual(self.entity.native_target_temperature,23)
        self.entity.async_write_ha_state.assert_not_called()

    async def test_failed_swing_ack_preserves_swing(self):
        await self.entity.async_turn_on()
        self.send.side_effect=OrviboBinaryError('sensitive')
        with self.assertRaises(HomeAssistantError):
            await self.entity.async_set_swing_mode('vertical')
        self.assertIsNone(self.entity.swing_mode)

    async def test_invalid_setting_does_not_send(self):
        await self.entity.async_turn_on()
        for action in [
            self.entity.async_set_temperature(temperature=16),
            self.entity.async_set_temperature(temperature=31),
            self.entity.async_set_fan_mode('turbo'),
            self.entity.async_set_swing_mode('horizontal'),
        ]:
            with self.assertRaises(HomeAssistantError):
                await action
        self.assertEqual(self.send.await_count,1)

    async def test_missing_hub_and_duplicate_hub_rejected(self):
        self.coord.data.devices=(self.vivax,)
        self.assertFalse(self.entity.available)
        with self.assertRaises(HomeAssistantError):
            await self.entity.async_turn_on()
        self.coord.data.devices=(self.vivax,self.hub,replace(self.hub,uid='dup'))
        self.assertFalse(self.entity.available)
        self.send.assert_not_awaited()


if __name__=='__main__':
    unittest.main()
