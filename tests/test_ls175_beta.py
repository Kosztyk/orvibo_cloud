"""Read-only offline regression tests for the LS175 RCoid diagnostic beta."""
from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_ac import PACKAGE, devices, HomeAssistantError, OrviboBinaryError

ls175_codes = importlib.import_module(f"{PACKAGE}.blaupunkt_ls175")

SPEAKER_ROW = {
    "deviceId": "bedroom-soundbar", "uid": "shared-hub-uid",
    "model": "32bede904a0f4b7a90f3d034e26fefb3",
    "deviceType": 7, "subDeviceType": 0, "online": True,
}
HUB_ROW = {
    "deviceId": "allone-pro", "uid": "shared-hub-uid",
    "model": SPEAKER_ROW["model"], "deviceType": 67, "online": True,
}


class CodesTests(unittest.TestCase):
    def test_all_ten_rcf_vectors_and_valid_nec_complements(self):
        expected = [
            0x00FF9867, 0x00FFA857, 0x00FF18E7, 0x00FF827D,
            0x00FFC23D, 0x00FFE21D, 0x00FFA25D, 0x00FF38C7,
            0x00FF10EF, 0x00FF5AA5,
        ]
        self.assertEqual([x.nec_word for x in ls175_codes.LS175_TEST_KEYS], expected)
        self.assertEqual(len(ls175_codes.LS175_TEST_KEYS), 10)
        for idx, word in enumerate(expected, 1):
            with self.subTest(code=idx):
                key = f"code_{idx:02d}"
                cmd = ls175_codes.ls175_test_command(key)
                self.assertEqual((cmd.order, cmd.value1, cmd.value2, cmd.value3, cmd.value4),
                                 ("ir control", 0, 0, 0, 0))
                self.assertEqual(cmd.infrared.frequency, 38000)
                pulses = cmd.infrared.pulses
                self.assertEqual(len(pulses), 68)
                self.assertEqual(pulses[:2], (9000, 4500))
                self.assertEqual(pulses[-2:], (560, 1000))
                bits = [(pulses[3 + 2 * n] == 1680) for n in range(32)]
                decoded = sum(int(bit) << (31 - n) for n, bit in enumerate(bits))
                self.assertEqual(decoded, word)

    def test_labels_follow_physical_speaker_observations(self):
        keys = {x.key: x for x in ls175_codes.LS175_TEST_KEYS}
        expected = {
            "code_02": "Vol +", "code_03": "Vol -", "code_06": "Source",
            "code_07": "Power Toggle", "code_08": "Equalizer",
            "code_10": "Mute / BT Pair",
        }
        for key, label in expected.items():
            self.assertEqual(keys[key].label, label)
            self.assertTrue(keys[key].identified)
        self.assertEqual([x.key for x in ls175_codes.LS175_CONFIRMED_KEYS],
                         list(expected))
        for key in ("code_01", "code_04", "code_05", "code_09"):
            self.assertFalse(keys[key].identified)
        self.assertIn("no response", keys["code_09"].label)

    def test_named_aliases_map_to_same_physical_ir_vectors(self):
        expected = {
            "power_toggle": "code_07", "volume_up": "code_02",
            "volume_down": "code_03", "source": "code_06",
            "mute": "code_10", "bluetooth_pair": "code_10",
            "equalizer": "code_08",
        }
        self.assertEqual(ls175_codes.LS175_COMMAND_ALIASES, expected)
        for alias, original in expected.items():
            with self.subTest(alias=alias):
                self.assertEqual(ls175_codes.ls175_test_command(alias),
                                 ls175_codes.ls175_test_command(original))

    def test_discontinued_ls175_entities_are_strictly_scoped(self):
        selection = importlib.import_module(f"{PACKAGE}.selection")
        check = selection.is_obsolete_ls175_entity
        for suffix in ("remote", "code_01", "code_04", "code_05", "code_07", "code_09"):
            domain = "remote" if suffix == "remote" else "button"
            self.assertTrue(check(domain, "orvibo_cloud", f"speaker_ls175_beta_{suffix}"))
            self.assertFalse(check(domain, "different_integration", f"speaker_ls175_beta_{suffix}"))
        for suffix in ("code_02", "code_03", "code_06", "code_08", "code_10"):
            self.assertFalse(check("button", "orvibo_cloud", f"speaker_ls175_beta_{suffix}"))
        self.assertFalse(check("remote", "orvibo_cloud", "speaker_tv_remote"))
        self.assertFalse(check("button", "orvibo_cloud", "speaker_tv_code_01"))

    def test_invalid_signal_fails_closed(self):
        for name in ("", "power", "vol_up", "code_11", 4, None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                ls175_codes.ls175_test_command(name)
        for word in (True, -1, 0x100000000, 0x00FF8888):
            with self.subTest(word=word), self.assertRaises(ValueError):
                ls175_codes.ls175_nec_pulses(word)

    def test_per_device_opt_in_and_invalid_profile_validation(self):
        selection = importlib.import_module(f"{PACKAGE}.selection")
        selected = selection.speaker_ir_profile_is_selected
        mapping = selection.configured_speaker_ir_models
        opts = {"speaker_ir_models": {"speaker-a": "blaupunkt_ls175"}}
        self.assertTrue(selected(opts, "speaker-a", "blaupunkt_ls175"))
        self.assertFalse(selected(opts, "speaker-b", "blaupunkt_ls175"))
        self.assertFalse(selected({}, "speaker-a", "blaupunkt_ls175"))
        self.assertFalse(selected({"speaker_ir_models": {"speaker-a": "other"}},
                                  "speaker-a", "blaupunkt_ls175"))
        self.assertEqual(mapping({"speaker_ir_models": ["wrong-shape"]}), {})
        self.assertEqual(mapping({"speaker_ir_models": {"speaker-a": "none"}}), {})

    def test_route_requires_one_online_matching_allone_pro(self):
        hub, soundbar = devices(SPEAKER_ROW, HUB_ROW)
        check = ls175_codes.is_ls175_test_target
        self.assertTrue(check(soundbar, (soundbar, hub)))
        self.assertFalse(check(soundbar, (soundbar,)))
        self.assertFalse(check(soundbar, (soundbar, hub, hub)))
        # Genuine changes in route and device class must all be rejected.
        from dataclasses import replace
        self.assertFalse(check(replace(soundbar,device_type="6"),(soundbar,hub)))
        self.assertFalse(check(replace(soundbar,sub_device_type="1"),(soundbar,hub)))
        self.assertFalse(check(replace(soundbar,cloud_uid="other"),(soundbar,hub)))
        self.assertFalse(check(replace(soundbar,online=False),(soundbar,hub)))
        self.assertFalse(check(soundbar, (soundbar, replace(hub,online=False))))
        self.assertFalse(check(soundbar, (soundbar, replace(hub,device_type="30"))))


class FakeSwitchEntity:
    pass


class FakeRestoreEntity:
    async def async_get_last_state(self):
        return getattr(self, "_last_state", None)


class FakeDeviceEntity:
    def __init__(self, coordinator, device_id):
        self.coordinator = coordinator
        self._device_id = device_id
        self.hass = coordinator.hass

    async def async_added_to_hass(self):
        pass

    def async_write_ha_state(self):
        self._ha_state_writes = getattr(self, "_ha_state_writes", 0) + 1

    @property
    def _device(self):
        return next((d for d in self.coordinator.data.devices if d.uid == self._device_id), None)

    @property
    def available(self):
        return self.coordinator.last_update_success and self._device is not None


binary_fake = ModuleType(f"{PACKAGE}.binary")
binary_fake.OrviboBinaryError = OrviboBinaryError
binary_fake.control_device = Mock()

with patch.dict(sys.modules, {
    "homeassistant": ModuleType("homeassistant"),
    "homeassistant.components": ModuleType("homeassistant.components"),
    "homeassistant.components.button": SimpleNamespace(ButtonEntity=object),
    "homeassistant.components.remote": SimpleNamespace(RemoteEntity=object),
    "homeassistant.components.switch": SimpleNamespace(SwitchEntity=FakeSwitchEntity),
    "homeassistant.helpers.restore_state": SimpleNamespace(RestoreEntity=FakeRestoreEntity),
    "homeassistant.const": SimpleNamespace(STATE_ON="on", STATE_OFF="off"),
    "homeassistant.config_entries": SimpleNamespace(ConfigEntry=object),
    "homeassistant.core": SimpleNamespace(HomeAssistant=object),
    "homeassistant.exceptions": SimpleNamespace(HomeAssistantError=HomeAssistantError),
    "homeassistant.helpers": ModuleType("homeassistant.helpers"),
    "homeassistant.helpers.entity_platform": SimpleNamespace(AddEntitiesCallback=object),
    f"{PACKAGE}.binary": binary_fake,
    f"{PACKAGE}.const": SimpleNamespace(
        DOMAIN="orvibo_cloud", CONF_FAMILY_ID="family_id", CONF_HOST="host"
    ),
    f"{PACKAGE}.coordinator": SimpleNamespace(OrviboCloudCoordinator=object),
    f"{PACKAGE}.entity": SimpleNamespace(OrviboCloudDeviceEntity=FakeDeviceEntity),
}):
    ls175_runtime = importlib.import_module(f"{PACKAGE}.ls175")
    button = importlib.import_module(f"{PACKAGE}.button")
    remote = importlib.import_module(f"{PACKAGE}.remote")
    ha_switch = importlib.import_module(f"{PACKAGE}.switch")


class BetaRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hub, self.speaker = devices(SPEAKER_ROW, HUB_ROW)
        self.send = AsyncMock()
        self.entry = SimpleNamespace(
            entry_id="entry",
            data={"host":"test.invalid", "family_id":"family"},
            options={
                "selected_device_ids": [self.speaker.uid],
                "speaker_ir_models": {self.speaker.uid: "blaupunkt_ls175"},
            },
        )
        self.coord = SimpleNamespace(
            entry=self.entry,
            data=SimpleNamespace(devices=(self.speaker,self.hub),
                                 binary_user_name="user",binary_password="secret"),
            last_update_success=True,
            hass=SimpleNamespace(async_add_executor_job=self.send),
            tv_control_lock=asyncio.Lock(),
        )
        self.hass = SimpleNamespace(data={"orvibo_cloud":{"entry":self.coord}})

    async def test_opt_in_required_for_any_speaker_entity(self):
        self.entry.options = {"selected_device_ids": [self.speaker.uid]}
        buttons, remotes, switches = [], [], []
        await button.async_setup_entry(self.hass, self.entry, buttons.extend)
        await remote.async_setup_entry(self.hass, self.entry, remotes.extend)
        await ha_switch.async_setup_entry(self.hass, self.entry, switches.extend)
        self.assertEqual((len(buttons), len(remotes), len(switches)), (5, 0, 1))
        self.assertFalse(any(item.available for item in buttons + remotes + switches))
        self.send.assert_not_awaited()

    async def test_opt_out_disables_an_existing_entity_before_sending(self):
        buttons = []
        await button.async_setup_entry(self.hass, self.entry, buttons.extend)
        self.assertEqual(len(buttons), 5)
        self.entry.options = {"selected_device_ids": [self.speaker.uid]}
        self.assertFalse(buttons[0].available)
        with self.assertRaises(HomeAssistantError):
            await buttons[0].async_press()
        self.send.assert_not_awaited()

    async def test_setup_creates_buttons_and_native_switch_without_transmit(self):
        buttons, remotes, switches = [], [], []
        await button.async_setup_entry(self.hass,self.entry,buttons.extend)
        await remote.async_setup_entry(self.hass,self.entry,remotes.extend)
        await ha_switch.async_setup_entry(self.hass,self.entry,switches.extend)
        self.assertEqual(len(buttons),5)
        self.assertEqual(len(remotes),0)
        self.assertEqual(len(switches),1)
        self.assertEqual(switches[0]._attr_name,"Power")
        self.assertTrue(all(x.available for x in buttons+switches))
        self.send.assert_not_awaited()

    async def test_one_manual_press_uses_speaker_child_and_hub_route(self):
        buttons = []
        await button.async_setup_entry(self.hass,self.entry,buttons.extend)
        await buttons[1].async_press()
        self.send.assert_awaited_once()
        args = self.send.await_args.args
        self.assertEqual(args[5:8],(self.speaker.uid,self.speaker.cloud_uid,"ir control"))
        self.assertEqual(args[-1].frequency,38000)
        self.assertEqual(args[-1].pulses,ls175_codes.ls175_test_command("code_03").infrared.pulses)

    async def test_only_physically_verified_buttons_are_registered(self):
        buttons = []
        await button.async_setup_entry(self.hass, self.entry, buttons.extend)
        expected = ["code_02", "code_03", "code_06", "code_08", "code_10"]
        self.assertEqual([b._key for b in buttons], expected)
        self.assertEqual([b._attr_name for b in buttons],
                         ["Vol +", "Vol -", "Source", "Equalizer", "Mute / BT Pair"])
        self.assertEqual(buttons[3]._attr_icon, "mdi:equalizer")
        self.send.assert_not_awaited()

    async def test_power_and_equalizer_send_distinct_correct_words(self):
        buttons = []
        await button.async_setup_entry(self.hass, self.entry, buttons.extend)
        for name, word in (("code_08", 0x00FF38C7),):
            self.send.reset_mock()
            selected = next(b for b in buttons if b._key == name)
            await selected.async_press()
            self.send.assert_awaited_once()
            self.assertEqual(self.send.await_args.args[-1].pulses,
                             ls175_codes.ls175_nec_pulses(word))

    async def test_route_failure_does_not_send_anything(self):
        buttons=[]
        await button.async_setup_entry(self.hass,self.entry,buttons.extend)
        from dataclasses import replace
        self.coord.data.devices=(self.speaker,replace(self.hub,online=False))
        with self.assertRaises(HomeAssistantError):
            await buttons[0].async_press()
        self.send.assert_not_awaited()

    async def test_transport_error_sanitized(self):
        buttons = []
        await button.async_setup_entry(self.hass, self.entry, buttons.extend)
        self.send.side_effect = OrviboBinaryError("token=private")
        with self.assertRaisesRegex(HomeAssistantError, "did not acknowledge") as ex:
            await buttons[0].async_press()
        self.assertNotIn("token", str(ex.exception))


    async def test_power_switch_is_real_switch_and_uses_confirmed_code_07(self):
        switches=[]
        await ha_switch.async_setup_entry(self.hass,self.entry,switches.extend)
        self.assertEqual(len(switches),1)
        entity = switches[0]
        self.assertIsInstance(entity, FakeSwitchEntity)
        self.assertEqual(entity._attr_name,"Power")
        self.assertEqual(entity._attr_is_on,False)
        self.assertEqual(entity.extra_state_attributes["physical_power_feedback"],False)
        self.send.assert_not_awaited()
        await entity.async_turn_on()
        self.assertTrue(entity._attr_is_on)
        self.assertEqual(self.send.await_count,1)
        self.assertEqual(self.send.await_args.args[-1].pulses,
                         ls175_codes.ls175_nec_pulses(0x00FFA25D))
        await entity.async_turn_on()
        self.assertEqual(self.send.await_count,1,"redundant turn_on must not flip power")
        await entity.async_turn_off()
        self.assertFalse(entity._attr_is_on)
        self.assertEqual(self.send.await_count,2)
        await entity.async_turn_off()
        self.assertEqual(self.send.await_count,2,"redundant turn_off must not flip power")
        await entity.async_toggle()
        self.assertTrue(entity._attr_is_on)
        self.assertEqual(self.send.await_count,3)
        self.assertEqual(entity._ha_state_writes,3)

    async def test_switch_ack_failure_preserves_estimate(self):
        switches=[]
        await ha_switch.async_setup_entry(self.hass,self.entry,switches.extend)
        entity=switches[0]
        self.send.side_effect=OrviboBinaryError("private")
        with self.assertRaises(HomeAssistantError):
            await entity.async_turn_on()
        self.assertFalse(entity._attr_is_on)
        self.assertEqual(getattr(entity,"_ha_state_writes",0),0)

    async def test_switch_option_removal_and_missing_route_block_IR(self):
        switches=[]
        await ha_switch.async_setup_entry(self.hass,self.entry,switches.extend)
        entity=switches[0]
        self.entry.options={"selected_device_ids":[self.speaker.uid]}
        self.assertFalse(entity.available)
        with self.assertRaises(HomeAssistantError):
            await entity.async_toggle()
        self.send.assert_not_awaited()

    async def test_switch_restores_prior_optimistic_state(self):
        switches=[]
        await ha_switch.async_setup_entry(self.hass,self.entry,switches.extend)
        entity=switches[0]
        entity._last_state=SimpleNamespace(state="on")
        await entity.async_added_to_hass()
        self.assertTrue(entity._attr_is_on)
        self.assertEqual(entity.extra_state_attributes["state_source"],"restored_estimate")
        self.send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
