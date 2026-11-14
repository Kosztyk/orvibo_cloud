"""Regression tests for narrowly scoped retired LS175 beta entities."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from test_ac import PACKAGE
import importlib

selection = importlib.import_module(f"{PACKAGE}.selection")
SRC = Path(__file__).resolve().parents[1] / "custom_components/orvibo_cloud"


class CleanupTests(TestCase):
    def test_cleanup_removes_only_obsolete_ls175_entities(self):
        """Execute the real cleanup body against a fake HA registry."""
        source = (SRC / "__init__.py").read_text()
        tree = ast.parse(source)
        cleanup = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "_async_cleanup_obsolete_ls175_entities"
        )
        # The module imports HA on real installations; compile only this pure
        # cleanup function to run it without a HA test environment.
        tiny = ast.Module(
            body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), cleanup],
            type_ignores=[],
        )
        items = []
        for domain, suffix in (
            ("remote", "remote"),
            ("button", "code_01"),
            ("button", "code_04"),
            ("button", "code_05"),
            ("button", "code_09"),
            ("button", "code_02"),
            ("button", "code_03"),
            ("button", "code_06"),
            ("button", "code_07"),
            ("button", "code_08"),
            ("button", "code_10"),
            ("remote", "tv_remote"),
        ):
            unique = f"test_ls175_beta_{suffix}" if suffix != "tv_remote" else "test_tv_remote"
            items.append(SimpleNamespace(
                domain=domain, platform="orvibo_cloud", unique_id=unique,
                entity_id=f"{domain}.{suffix}",
            ))
        items.append(SimpleNamespace(
            domain="remote", platform="other_integration",
            unique_id="test_ls175_beta_remote", entity_id="remote.unrelated",
        ))
        removed = []
        registry = SimpleNamespace(async_remove=removed.append)
        fake_er = SimpleNamespace(
            async_get=lambda hass: registry,
            async_entries_for_config_entry=lambda reg, entry_id: tuple(items),
        )
        scope = {
            "er": fake_er,
            "is_obsolete_ls175_entity": selection.is_obsolete_ls175_entity,
        }
        ast.fix_missing_locations(tiny)
        exec(compile(tiny, str(SRC / "__init__.py"), "exec"), scope)
        scope["_async_cleanup_obsolete_ls175_entities"](
            object(), SimpleNamespace(entry_id="entry"),
        )
        self.assertEqual(
            removed,
            ["remote.remote", "button.code_01", "button.code_04",
             "button.code_05", "button.code_09", "button.code_07"],
        )

    def test_original_options_flow_has_not_been_replaced(self):
        # Avoid depending on another archive when tests are run by the user.
        source = (SRC / "config_flow.py").read_text()
        self.assertIn("async_step_devices", source)
        self.assertIn("async_step_area", source)
        self.assertIn("_rf_options_from_input", source)
        self.assertIn("speaker_ir_model", source)
        self.assertNotIn('"advanced_settings"', source)
