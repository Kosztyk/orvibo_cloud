"""Regression checks for the LS175 options persistence and stale entity fix."""
from pathlib import Path
import ast
import unittest

SRC = Path(__file__).resolve().parents[1] / "custom_components/orvibo_cloud"

class LS175OptionsFlowRegression(unittest.TestCase):
    def test_original_full_wizard_restored(self):
        source = (SRC / "config_flow.py").read_text()
        module = ast.parse(source)
        cls = next(x for x in module.body if isinstance(x, ast.ClassDef)
                   and x.name == "OrviboCloudOptionsFlow")
        steps = [x.name for x in cls.body if isinstance(x, ast.AsyncFunctionDef)]
        self.assertEqual(steps, ["async_step_init", "async_step_devices", "async_step_area"])
        init = next(x for x in cls.body if isinstance(x, ast.AsyncFunctionDef)
                    and x.name == "async_step_init")
        body = ast.get_source_segment(source, init)
        self.assertIn('step_id="init"', body)
        self.assertIn('return await self.async_step_devices()', body)
        self.assertIn('configured_device_areas(', body)
        self.assertIn('configured_rf_blind_options(', body)
        self.assertIn('configured_speaker_ir_models(', body)
        for name in ('CONF_HOST', 'tv_profile', 'CONF_RAW_EVENT_CAPTURE'):
            self.assertIn(name, body)
        self.assertNotIn('advanced_settings', body)
        self.assertNotIn('\"speaker_ir_model\"', body)

    def test_device_and_rf_and_speaker_options_saved_at_last_step(self):
        source = (SRC / 'config_flow.py').read_text()
        self.assertIn('CONF_SELECTED_DEVICE_IDS: self._selected_ids', source)
        self.assertIn('CONF_DEVICE_AREAS:', source)
        self.assertIn('CONF_RF_BLIND_OPTIONS:', source)
        self.assertIn('CONF_SPEAKER_IR_MODELS:', source)
        self.assertIn('self._speaker_ir_models[device.uid] = speaker_model', source)
        self.assertIn('self._rf_options[device.uid] = _rf_options_from_input(user_input)', source)
        self.assertIn('if self._area_index >= len(devices):', source)

    def test_stable_entity_ids_and_explicit_opt_in(self):
        for filename in ('button.py', 'remote.py'):
            source = (SRC / filename).read_text()
            mod = ast.parse(source)
            setup = next(x for x in mod.body if isinstance(x, ast.AsyncFunctionDef)
                         and x.name == 'async_setup_entry')
            setup_src = ast.get_source_segment(source, setup)
            self.assertNotIn('speaker_ir_profile_is_selected(', setup_src)
        self.assertNotIn('OrviboLS175TestRemote', (SRC / 'remote.py').read_text())
        self.assertIn('_async_cleanup_obsolete_ls175_entities', (SRC / '__init__.py').read_text())
        self.assertIn('_ls175_beta_', (SRC / 'button.py').read_text())
        assert 'and speaker_ir_profile_is_selected(' in (SRC / 'ls175.py').read_text()

    def test_confirmed_button_names_have_no_test_prefix(self):
        from pathlib import Path
        src = (SRC / 'button.py').read_text()
        self.assertIn('self._attr_name = key.label', src)
        self.assertNotIn('self._attr_name = f"Blaupunkt LS 175 Test', src)
        code = (SRC / 'blaupunkt_ls175.py').read_text()
        for label in ('"Vol +"', '"Vol -"', '"Source"', '"Equalizer"', '"Mute / BT Pair"'):
            self.assertIn(label, code)
        self.assertIn('"Test Code 01"', code)
        self.assertIn('LS175_CONFIRMED_KEYS', src)
        self.assertIn('if key.key != "code_07"', src)
        self.assertIn('OrviboLS175PowerSwitch', (SRC / 'switch.py').read_text())

    def test_all_options_steps_are_translated(self):
        import json
        j = json.loads((SRC / 'strings.json').read_text())
        t = j['options']['step']
        self.assertEqual(set(t), {'init', 'devices', 'area'})
        self.assertIn('host', t['init']['data'])
        self.assertIn('tv_profile', t['init']['data'])
        self.assertIn('raw_event_capture', t['init']['data'])
        self.assertIn('selected_device_ids', t['devices']['data'])
        self.assertIn('remember_assumed_state', t['area']['data'])
        self.assertIn('restore_assumed_state', t['area']['data'])
        self.assertIn('assumed_state_expiry_minutes', t['area']['data'])
        self.assertIn('speaker_ir_model', t['area']['data'])
        self.assertEqual(j, json.loads((SRC / 'translations/en.json').read_text()))

if __name__ == '__main__':
    unittest.main()
