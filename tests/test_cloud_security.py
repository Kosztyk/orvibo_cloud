"""Regression tests for the beta's cloud and Home Assistant security gates."""

import asyncio
from dataclasses import replace
from importlib import import_module, util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch


COMPONENT = Path(__file__).resolve().parents[1] / "custom_components/orvibo_cloud"
PACKAGE = "_orvibo_cloud_security_tests"
HOST = "homemate.orvibo.com"


class CoordinatorStub:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, **kwargs):
        self.hass = hass
        self.last_update_success = False

    async def async_config_entry_first_refresh(self):
        await self._async_setup()
        self.data = await self._async_update_data()
        self.last_update_success = True

    def async_add_listener(self, listener):
        return MagicMock()


spec = util.spec_from_file_location(
    PACKAGE, COMPONENT / "__init__.py", submodule_search_locations=[str(COMPONENT)]
)
integration = util.module_from_spec(spec)
with patch.dict(sys.modules, {
    PACKAGE: integration,
    "homeassistant": ModuleType("homeassistant"),
    "homeassistant.config_entries": SimpleNamespace(ConfigEntry=object),
    "homeassistant.core": SimpleNamespace(HomeAssistant=object, callback=lambda func: func),
    "homeassistant.const": SimpleNamespace(CONF_EMAIL="email", Platform=MagicMock()),
    "homeassistant.exceptions": SimpleNamespace(
        ConfigEntryAuthFailed=type("ConfigEntryAuthFailed", (Exception,), {}),
        HomeAssistantError=type("HomeAssistantError", (Exception,), {}),
    ),
    "homeassistant.helpers": SimpleNamespace(device_registry=MagicMock(), entity_registry=MagicMock()),
    "homeassistant.helpers.aiohttp_client": SimpleNamespace(async_get_clientsession=MagicMock()),
    "homeassistant.helpers.dispatcher": SimpleNamespace(async_dispatcher_send=Mock()),
    "homeassistant.helpers.update_coordinator": SimpleNamespace(
        DataUpdateCoordinator=CoordinatorStub, UpdateFailed=type("UpdateFailed", (Exception,), {}),
    ),
}):
    spec.loader.exec_module(integration)
    api = import_module(f"{PACKAGE}.api")
    binary = import_module(f"{PACKAGE}.binary")
    coordinator_module = import_module(f"{PACKAGE}.coordinator")
    diagnostics = import_module(f"{PACKAGE}.diagnostics")
    protocol = import_module(f"{PACKAGE}.protocol")


class RedirectTests(unittest.IsolatedAsyncioTestCase):
    async def test_oauth_family_and_readtable_refuse_redirects_before_parsing(self):
        for status in (302, 307, 308):
            for path, method, arguments in (
                ("_async_oauth", "get", ("email", "password")),
                ("_async_families", "post", ("token", "user")),
                ("_async_readtable_payload", "post", ("token", "user", "family")),
            ):
                with self.subTest(status=status, path=path):
                    session = MagicMock()
                    request = getattr(session, method)
                    response = request.return_value.__aenter__.return_value
                    response.status = status
                    with self.assertRaisesRegex(api.OrviboProtocolError, str(status)):
                        await getattr(api.OrviboCloudClient(session), path)(HOST, *arguments)
                    self.assertIs(request.call_args.kwargs["allow_redirects"], False)
                    response.json.assert_not_called()
                    response.raise_for_status.assert_not_called()

    async def test_readtable_omits_untrusted_error_text(self):
        session = MagicMock()
        response = session.post.return_value.__aenter__.return_value
        response.status = 200
        response.raise_for_status = MagicMock()
        response.json = AsyncMock(return_value={"status": "private-cloud-data"})
        with self.assertRaisesRegex(api.OrviboProtocolError, "non_numeric") as caught:
            await api.OrviboCloudClient(session)._async_readtable_payload(
                HOST, "token", "user", "family"
            )
        self.assertNotIn("private-cloud-data", str(caught.exception))


class IntegrationSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.entry = SimpleNamespace(
            entry_id="entry", data={
                "host": HOST, "email": "private-user@example.invalid",
                "family_id": "private-family-id", "password_hash": "private-password-hash",
                "user_id": "private-user-id", "future_secret": "private-reserved-secret",
            }, options={}, async_on_unload=MagicMock(), add_update_listener=MagicMock(),
        )
        self.device = protocol.OrviboDevice(
            uid="private-device-id", name="private-device-label", model="private-model",
            device_type="5", sub_device_type="2", room="private-room",
            parent_uid="private-parent", online=True, cloud_uid="private-route",
            ir_profile_id="7579", value1=1234567890,
        )
        self.account = api.OrviboAccount(
            host=HOST, user_id="private-user-id", access_token="private-token",
            families=(protocol.OrviboFamily("private-family-id", "private-family-label"),),
            devices=(self.device,), binary_user_name="private-binary-user",
            binary_password="private-binary-password",
        )
        async def executor_job(func, *args):
            return func(*args)
        self.hass = SimpleNamespace(
            data={}, config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock()),
            async_add_executor_job=executor_job,
        )

    async def setup(self, pins=frozenset(), *, invalid=False):
        with (
            patch.object(integration, "_async_register_devices"),
            patch.object(integration, "_async_cleanup_obsolete_ls175_entities"),
            patch.object(integration.OrviboCloudClient, "async_discover", new=AsyncMock(
                return_value=self.account
            )),
            patch.object(coordinator_module, "load_binary_server_pins", return_value=pins,
                  side_effect=binary.OrviboServerIdentityError("Bad digest") if invalid else None),
            patch.object(integration, "OrviboRawEventCapture") as capture,
        ):
            self.assertTrue(await integration.async_setup_entry(self.hass, self.entry))
        return self.hass.data["orvibo_cloud"]["entry"], capture

    async def test_default_setup_keeps_binary_credentials_without_pin_configuration(self):
        coordinator, capture = await self.setup()
        self.assertIs(coordinator.last_update_success, True)
        self.assertEqual(coordinator.data.devices, self.account.devices)
        self.assertEqual(coordinator.data.binary_user_name, self.account.binary_user_name)
        self.assertEqual(coordinator.data.binary_password, self.account.binary_password)
        self.assertEqual(coordinator.binary_server_trust, "vendor_ca")
        capture.assert_not_called()

    async def test_invalid_pin_keeps_rest_and_blocks_binary_even_with_capture_enabled(self):
        self.entry.options["raw_event_capture"] = True
        coordinator, capture = await self.setup(invalid=True)
        self.assertIs(coordinator.last_update_success, True)
        self.assertEqual(coordinator.data.devices, self.account.devices)
        self.assertEqual(coordinator.data.binary_password, "")
        self.assertEqual(coordinator.data.binary_user_name, "")
        self.assertEqual(coordinator.binary_server_trust, "invalid_pin")
        capture.assert_not_called()

    async def test_setup_keeps_existing_verified_pin(self):
        approved = frozenset({"1" * 64})
        coordinator, capture = await self.setup(approved)
        self.assertEqual(coordinator.data.binary_password, self.account.binary_password)
        self.assertEqual(coordinator.binary_server_trust, "pin_configured")
        capture.assert_not_called()

    async def test_default_listener_starts_for_explicit_capture_or_selected_door(self):
        self.entry.options["raw_event_capture"] = True
        _, capture = await self.setup()
        capture.return_value.start.assert_called_once_with()
        self.assertIsNone(capture.call_args.kwargs["on_reconnect"])
        self.entry.options["raw_event_capture"] = False
        door = replace(self.device, properties={"door_status": "closed"})
        self.account = replace(self.account, devices=(door,))
        coordinator, capture = await self.setup()
        capture.return_value.start.assert_called_once_with()
        self.assertEqual(capture.call_args.kwargs["door_status_signal"], coordinator.door_status_signal)
        self.assertEqual(capture.call_args.kwargs["on_reconnect"], coordinator.async_resync_doors)
        self.entry.options["selected_device_ids"] = ["some-other-device"]
        _, capture = await self.setup()
        capture.assert_not_called()

    async def test_malformed_table_cannot_replace_last_successful_snapshot(self):
        coordinator, _ = await self.setup()
        good_snapshot = coordinator.data
        session = MagicMock()
        response = session.post.return_value.__aenter__.return_value
        response.status = 200
        response.raise_for_status = Mock()
        coordinator.client = api.OrviboCloudClient(session)
        malformed_tables = (
            {"status": 0},
            {"status": 0, "data": {}},
            {"status": 0, "data": {"device": None}},
            {"status": 0, "data": {"device": {"not": "an array"}}},
            {"status": 0, "data": {"device": [{"deviceId": "valid"}, "bad row"]}},
            {"status": 0, "data": {"device": [{"deviceId": ["wrong identifier type"]}]}},
            {"status": 0, "data": {"device": [], "deviceStatus": "bad table"}},
        )
        with (
            patch.object(coordinator.client, "_async_oauth", new=AsyncMock(return_value=("token", "user"))),
            patch.object(coordinator.client, "_async_families", new=AsyncMock(return_value=self.account.families)),
        ):
            for payload in malformed_tables:
                with self.subTest(payload=payload):
                    response.json = AsyncMock(return_value=payload)
                    with self.assertRaisesRegex(coordinator_module.UpdateFailed, "malformed device table"):
                        await coordinator._async_update_data()
                    self.assertIs(coordinator.data, good_snapshot)

            # An explicit empty device table is a successful snapshot.
            response.json = AsyncMock(return_value={"status": 0, "data": {"device": []}})
            updated = await coordinator._async_update_data()
            self.assertEqual(updated.devices, ())
            self.assertGreater(updated.device_snapshot_started_ns, 0)
            self.assertIsNone(coordinator.device_discovery_error)

    async def test_reconnect_invalidates_cached_door_observations_and_schedules_refresh(self):
        coordinator, _ = await self.setup()
        coordinator.async_update_listeners = Mock()
        coordinator.async_request_refresh = AsyncMock()
        self.entry.async_create_task = Mock(
            side_effect=lambda hass, coro, name: asyncio.create_task(coro)
        )

        coordinator.async_resync_doors(123)
        await asyncio.sleep(0)
        self.assertEqual(coordinator.last_push_reconnect_ns, 123)
        coordinator.async_update_listeners.assert_called_once_with()
        coordinator.async_request_refresh.assert_awaited_once_with()

    async def test_diagnostics_allowlist_omits_personal_and_untrusted_protocol_data(self):
        coordinator, _ = await self.setup()
        coordinator.device_discovery_error = "private-vendor-reply"
        output = await diagnostics.async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(output["entry"], {"host": HOST})
        self.assertEqual(output["device_discovery_error"], "discovery_failed")
        self.assertEqual(output["devices"][0]["ir_profile_id"], "7579")
        self.assertIs(output["devices"][0]["online"], True)
        self.assertNotIn("private-", json.dumps(output))
        self.assertNotIn("1234567890", json.dumps(output))
