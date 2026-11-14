"""Diagnostics support for Orvibo Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant

from .blaupunkt_ls175 import is_ls175_test_target
from .const import CONF_PASSWORD_HASH, CONF_USER_ID, DOMAIN
from .control import is_allone_tv, is_rf_curtain, tv_commands_for_profile
from .coordinator import OrviboCloudCoordinator
from .protocol import ac_hub_matches
from .selection import (
    SPEAKER_MODEL_BLAUPUNKT_LS175, configured_speaker_ir_models,
    device_is_selected, speaker_ir_profile_is_selected,
)
from .ac_profiles import ac_profile

_TO_REDACT = {CONF_PASSWORD_HASH, CONF_USER_ID, CONF_EMAIL}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return account diagnostics without credentials or OAuth tokens."""

    coordinator: OrviboCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": async_redact_data(dict(entry.data), _TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "family_count": len(coordinator.data.families),
        "device_count": len(coordinator.data.devices),
        "device_discovery_error": coordinator.device_discovery_error,
        "privacy_device_discovery_error": (
            coordinator.privacy_device_discovery_error
        ),
        "families": [
            {"family_id": "**REDACTED**", "name": family.name}
            for family in coordinator.data.families
        ],
        "devices": [
            {
                "uid": "**REDACTED**",
                "name": device.name,
                "model": device.model,
                "device_type": device.device_type,
                "sub_device_type": device.sub_device_type,
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
                "room": device.room,
                "parent_uid": "**REDACTED**" if device.parent_uid else "",
                "online": device.online,
                "value1": device.value1,
                "value2": device.value2,
                "value3": device.value3,
                "value4": device.value4,
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
                    if is_allone_tv(device, coordinator.data.devices) else None
                ),
                "selected": device_is_selected(entry.options, device.uid),
            }
            for device in coordinator.data.devices
        ],
    }
