"""Diagnostics support for Orvibo Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .blaupunkt_ls175 import is_ls175_test_target
from .const import CONF_HOST, DOMAIN
from .control import is_allone_tv, is_rf_curtain, tv_commands_for_profile
from .coordinator import OrviboCloudCoordinator
from .protocol import ORVIBO_HOSTS, ac_hub_matches
from .selection import (
    SPEAKER_MODEL_BLAUPUNKT_LS175, configured_speaker_ir_models,
    device_is_selected, speaker_ir_profile_is_selected,
)


def _diagnostic_type(value: str) -> str | None:
    """Keep short vendor type codes and omit free-form cloud strings."""
    return value if len(value) <= 8 and value.isascii() and value.isdecimal() else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return an allowlist of non-identifying account and routing data."""

    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data.get(CONF_HOST)
    return {
        "entry": {CONF_HOST: host} if host in ORVIBO_HOSTS else {},
        "binary_server_trust": coordinator.binary_server_trust,
        "last_update_success": coordinator.last_update_success,
        "family_count": len(coordinator.data.families),
        "device_count": len(coordinator.data.devices),
        "device_discovery_error": (
            "discovery_failed" if coordinator.device_discovery_error else None
        ),
        "privacy_device_discovery_error": (
            "discovery_failed" if coordinator.privacy_device_discovery_error else None
        ),
        "devices": [
            {
                "device_type": _diagnostic_type(device.device_type),
                "sub_device_type": _diagnostic_type(device.sub_device_type),
                "ir_profile_id": device.ir_profile_id or None,
                "ac_ir_encoder": (
                    "midea_48_kaysun_swing"
                    if (device.device_type, device.sub_device_type, device.ir_profile_id)
                    == ("5", "2", "7579") else None
                ),
                "ls175_beta": (
                    {
                        "target_type": "7/0",
                        "eligible_raw_ir_test_route": is_ls175_test_target(
                            device, coordinator.data.devices
                        ),
                        "matching_online_allone_hub": any(
                            hub.device_type == "67"
                            and hub.cloud_uid == device.cloud_uid
                            and hub.model == device.model
                            and hub.online is not False
                            for hub in coordinator.data.devices
                        ),
                        "selected_ir_model": configured_speaker_ir_models(
                            entry.options
                        ).get(device.uid),
                        "configuration_saved": (
                            device.uid in configured_speaker_ir_models(entry.options)
                        ),
                        "profile_enabled": speaker_ir_profile_is_selected(
                            entry.options, device.uid, SPEAKER_MODEL_BLAUPUNKT_LS175
                        ),
                        "verified_physical_ir": False,
                    }
                    if (device.device_type, device.sub_device_type) == ("7", "0")
                    else None
                ),
                "ac_hub_matches": (
                    ac_hub_matches(device, coordinator.data.devices)
                    if (device.device_type, device.sub_device_type) == ("5", "2")
                    else []
                ),
                "online": device.online,
                "has_control_uid": bool(device.cloud_uid),
                "control_profile": (
                    "allone_rf" if is_rf_curtain(device, coordinator.data.devices)
                    else "allone_tv" if is_allone_tv(device, coordinator.data.devices)
                    else "position" if device.device_type == "34" else None
                ),
                "tv_commands": (
                    [command.key for command in tv_commands_for_profile(
                        entry.options.get("tv_profile", "lg")
                    )]
                    if is_allone_tv(device, coordinator.data.devices) else []
                ),
                "tv_profile": (
                    entry.options.get("tv_profile", "lg")
                    if (
                        is_allone_tv(device, coordinator.data.devices)
                        and entry.options.get("tv_profile", "lg") in ("lg", "stored")
                    ) else None
                ),
                "selected": device_is_selected(entry.options, device.uid),
            }
            for device in coordinator.data.devices
        ],
    }
