"""Diagnostics support for Orvibo Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD_HASH, CONF_USER_ID, DOMAIN
from .control import is_allone_tv, is_rf_curtain, tv_commands_for_profile
from .coordinator import OrviboCloudCoordinator
from .selection import device_is_selected

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
