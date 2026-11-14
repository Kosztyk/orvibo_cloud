"""Device selection helpers for ORVIBO config entries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

CONF_SELECTED_DEVICE_IDS = "selected_device_ids"
CONF_DEVICE_AREAS = "device_areas"


def selected_device_ids(
    options: Mapping[str, Any],
    available_device_ids: Iterable[str],
) -> set[str]:
    """Return selected IDs, defaulting legacy entries to every available device."""

    available = {str(device_id) for device_id in available_device_ids}
    if CONF_SELECTED_DEVICE_IDS not in options:
        return available
    configured = options.get(CONF_SELECTED_DEVICE_IDS)
    if not isinstance(configured, (list, tuple, set)):
        return set()
    return {str(device_id) for device_id in configured} & available


def device_is_selected(options: Mapping[str, Any], device_id: str) -> bool:
    """Return whether one device should be exposed by the integration."""

    if CONF_SELECTED_DEVICE_IDS not in options:
        return True
    configured = options.get(CONF_SELECTED_DEVICE_IDS)
    if not isinstance(configured, (list, tuple, set)):
        return False
    return device_id in {str(value) for value in configured}


def configured_device_areas(options: Mapping[str, Any]) -> dict[str, str | None]:
    """Return the configured HA area ID for each selected device."""

    configured = options.get(CONF_DEVICE_AREAS)
    if not isinstance(configured, Mapping):
        return {}
    areas: dict[str, str | None] = {}
    for device_id, area_id in configured.items():
        if area_id is None:
            areas[str(device_id)] = None
        elif isinstance(area_id, str) and area_id:
            areas[str(device_id)] = area_id
    return areas


# Optional IR profile for each independently registered HomeMate speaker child.
# No speaker profile is enabled implicitly by device type or display name.
CONF_SPEAKER_IR_MODELS = "speaker_ir_models"
SPEAKER_MODEL_NONE = "none"
SPEAKER_MODEL_BLAUPUNKT_LS175 = "blaupunkt_ls175"
SUPPORTED_SPEAKER_IR_MODELS = frozenset({SPEAKER_MODEL_BLAUPUNKT_LS175})


def configured_speaker_ir_models(options: Mapping[str, Any]) -> dict[str, str]:
    """Read supported, explicit per-device profile selections only."""
    mapping = options.get(CONF_SPEAKER_IR_MODELS)
    if not isinstance(mapping, Mapping):
        return {}
    return {
        uid: profile for uid, profile in mapping.items()
        if isinstance(uid, str) and uid
        and isinstance(profile, str) and profile in SUPPORTED_SPEAKER_IR_MODELS
    }


def speaker_ir_profile_is_selected(
    options: Mapping[str, Any], device_id: str, profile: str
) -> bool:
    """Never infer LS175 model from type 7 or shared Allone Pro model hash."""
    return configured_speaker_ir_models(options).get(device_id) == profile


_OBSOLETE_LS175_TEST_CODES = frozenset({"01", "04", "05", "07", "09"})


def is_obsolete_ls175_entity(domain: str, platform: str, unique_id: str) -> bool:
    """Identify only the obsolete beta entities, never other ORVIBO entities.

    The five remaining LS175 buttons keep their existing unique IDs. The old
    Code 07 power button is retired in favor of a native switch entity.
    """
    if platform != "orvibo_cloud" or not isinstance(unique_id, str):
        return False
    if domain == "remote":
        return unique_id.endswith("_ls175_beta_remote")
    if domain == "button":
        return any(
            unique_id.endswith(f"_ls175_beta_code_{code}")
            for code in _OBSOLETE_LS175_TEST_CODES
        )
    return False
