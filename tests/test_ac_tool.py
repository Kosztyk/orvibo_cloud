"""Regression tests for repaired BAXI offline diagnostic argument paths."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1] / "tools/check_baxi_route.py"
spec = importlib.util.spec_from_file_location("orvibo_beta_baxi_tool", TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class DiagnosticToolTests(unittest.TestCase):
    def test_read_only_by_default(self):
        args=tool.make_parser().parse_args([])
        self.assertFalse(tool.wants_scene_lookup(args))

    def test_extras_uses_scene_lookup(self):
        args=tool.make_parser().parse_args(["--probe-extras"])
        self.assertTrue(args.probe_extras)
        self.assertTrue(tool.wants_scene_lookup(args))

    def test_scene_modes_are_routed(self):
        for option in ("--scene-off", "--scene-test-off", "--scene-test-on"):
            with self.subTest(option=option):
                args=tool.make_parser().parse_args([option])
                self.assertTrue(tool.wants_scene_lookup(args))

    def test_cool_probe_uses_scene_lookup(self):
        args=tool.make_parser().parse_args(["--probe-cool","19"])
        self.assertTrue(tool.wants_scene_lookup(args))
        self.assertEqual(args.probe_cool,19)

    def test_scene_action_returns_only_selected_scene(self):
        payload={"data":{"scene":[{"sceneNo":"11","sceneName":"BAXI prueba OFF"},
                                   {"sceneNo":"12","sceneName":"other"}],
                         "sceneBind":[{"sceneNo":"11","order":"ir control"},
                                      {"sceneNo":"12","order":"ir control"}]}}
        actions=tool.scene_actions(payload,"BAXI prueba OFF")
        self.assertEqual(len(actions),1)
        self.assertEqual(len(actions[0]),1)
        self.assertEqual(tool.scene_signal(actions[0])["ir_control"],True)

    def test_invalid_or_ambiguous_scene_never_returns_command(self):
        self.assertIsNone(tool.baxi_scene_command([],()))
        self.assertIsNone(tool.baxi_scene_command([{"order":"ir control"}],()))

    def test_no_command_without_explicit_confirmation(self):
        # This runs no network activity, even if an envelope were provided.
        with patch("builtins.input",return_value="NO"):
            self.assertEqual(tool.send_once([tuple()],label="fake"),1)

    def test_no_command_for_multiple_targets(self):
        with patch("builtins.input",side_effect=AssertionError("asked unnecessarily")):
            self.assertEqual(tool.send_once([tuple(),tuple()],label="fake"),1)


if __name__ == "__main__":
    unittest.main()
