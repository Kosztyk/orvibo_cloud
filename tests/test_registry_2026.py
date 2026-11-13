"""Regression coverage for HA 2026.11 device-registry deprecations."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/orvibo_cloud"


@dataclass
class FakeDevice:
    id: str
    identifiers: set[tuple[str, str]]
    area_id: str | None = None


class FakeRegistry:
    def __init__(self):
        self.entries: dict[str, FakeDevice] = {}
        self.count = 0
        self.removed: list[str] = []

    def async_get_or_create(self, *, config_entry_id, identifiers, **kwargs):
        identifier, = identifiers
        if existing := self.entries.get(identifier[1]):
            return existing
        self.count += 1
        d = FakeDevice(f"ha-device-id-{self.count}", identifiers)
        if "via_device_id" in kwargs:
            assert kwargs["via_device_id"] in [p.id for p in self.entries.values()]
        self.entries[identifier[1]] = d
        return d

    def async_get_device_by_identifier(self, identifier, config_entry_id):
        return self.entries.get(identifier[1])

    def async_remove_device(self, device_id):
        self.removed.append(device_id)
        for key, entry in list(self.entries.items()):
            if entry.id == device_id:
                del self.entries[key]

    def async_update_device(self, device_id, *, area_id):
        for d in self.entries.values():
            if d.id == device_id:
                d.area_id = area_id


class RegistryMigrationTests(unittest.TestCase):
    def test_no_legacy_registry_api_in_any_integration_file(self):
        for f in SOURCE.glob("*.py"):
            content = f.read_text()
            self.assertNotIn("via_device=", content, f.name)
            self.assertNotIn("async_get_device(", content, f.name)
            self.assertNotIn("remove_config_entry_id=", content, f.name)
            self.assertNotIn(".config_entries\n", content, f.name)

    def test_parent_link_uses_scoped_ha_device_id(self):
        for f in ("__init__.py", "entity.py", "cover.py", "light.py"):
            content = (SOURCE / f).read_text()
            self.assertIn("via_device_id=", content, f)
            self.assertNotIn("via_device=", content, f)

    def test_selected_devices_keep_existing_registry_ids_and_areas(self):
        source = (SOURCE / "__init__.py").read_text()
        tree = ast.parse(source)
        method = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "_async_register_devices")
        module = ast.Module(body=[method], type_ignores=[])
        registry = FakeRegistry()
        registry.entries["account"] = FakeDevice("account-ha-id", {("orvibo_cloud", "account")})
        registry.entries["old-removed"] = FakeDevice("old-ha-id", {("orvibo_cloud", "old-removed")})
        registry.entries["selected"] = FakeDevice("selected-ha-id", {("orvibo_cloud", "selected")}, "kitchen")
        er_registry = SimpleNamespace(async_remove=Mock())
        remove_entities = Mock(return_value=[])
        dr = SimpleNamespace(async_get=lambda hass: registry,
                             async_entries_for_config_entry=lambda reg,entry_id:list(reg.entries.values()))
        er = SimpleNamespace(async_get=lambda hass: er_registry,
                             async_entries_for_device=remove_entities)
        env = dict(HomeAssistant=object, ConfigEntry=object, OrviboCloudCoordinator=object,
                   dr=dr, er=er, DOMAIN="orvibo_cloud", selected_device_ids=lambda opts,avail: {"selected"},
                   configured_device_areas=lambda opts: {"selected":"bedroom"},
                   device_is_selected=lambda opts, uid:uid=="selected")
        exec(compile(module, "_async_register_devices", "exec"), env)
        register=env["_async_register_devices"]
        entry = SimpleNamespace(entry_id="entry", data={"user_id":"account"},options={})
        device = SimpleNamespace(uid="selected",model="hub-model",device_type="67",name="unit",room="bedroom")
        coord = SimpleNamespace(data=SimpleNamespace(devices=(device,)))
        register(object(),entry,coord)
        self.assertEqual(registry.entries["selected"].id,"selected-ha-id")
        self.assertEqual(registry.entries["selected"].area_id,"kitchen")
        self.assertEqual(registry.entries["account"].id,"account-ha-id")
        self.assertNotIn("old-removed",registry.entries)
        self.assertIn("old-ha-id",registry.removed)
        register(object(),entry,coord)
        self.assertEqual(registry.entries["selected"].id,"selected-ha-id")
        self.assertEqual(registry.entries["selected"].area_id,"kitchen")


if __name__ == "__main__":
    unittest.main()
