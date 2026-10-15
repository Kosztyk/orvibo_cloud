"""Pure command mappings verified against the current ORVIBO app."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .protocol import OrviboDevice

_TUNABLE_LIGHT_SUB_DEVICE_TYPES = {"4", "6", "13"}
_PROPERTY_LIGHT_MODELS = {
    "294339fdc9b04613bb6cf1569305b78c",
    "71b94d0309094d1e9c678e4c21bbf878",
    "f731c19a484c419282051494ceecd66a",
}


@dataclass(frozen=True, slots=True)
class OrviboInfrared:
    """Carrier frequency in Hz and alternating mark/space times in microseconds."""

    frequency: int
    pulses: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class OrviboControlCommand:
    """Values carried by an ORVIBO cmd=15 device command."""

    order: str
    value1: int
    value2: int = 0
    value3: int = 0
    value4: int = 0
    properties: Mapping[str, Any] | None = None
    infrared: OrviboInfrared | None = None


@dataclass(frozen=True, slots=True)
class OrviboTVCommand:
    """One stored TV key from HomeMate's activity_tv_controller layout."""

    key: str
    name: str
    order: str | None
    icon: str


TV_COMMANDS = (
    OrviboTVCommand("power_toggle", "Power toggle", "310110", "mdi:power"),
    OrviboTVCommand("mute", "Mute", "310112", "mdi:volume-mute"),
    OrviboTVCommand("volume_up", "Volume up", "310113", "mdi:volume-plus"),
    OrviboTVCommand("volume_down", "Volume down", "310114", "mdi:volume-minus"),
    OrviboTVCommand("channel_up", "Channel up", "310115", "mdi:chevron-up"),
    OrviboTVCommand("channel_down", "Channel down", "310116", "mdi:chevron-down"),
    OrviboTVCommand("menu", "Menu", "310118", "mdi:menu"),
    OrviboTVCommand("input", "Input", "310126", "mdi:video-input-hdmi"),
    OrviboTVCommand("up", "Up", "310120", "mdi:arrow-up"),
    OrviboTVCommand("down", "Down", "310121", "mdi:arrow-down"),
    OrviboTVCommand("left", "Left", "310122", "mdi:arrow-left"),
    OrviboTVCommand("right", "Right", "310123", "mdi:arrow-right"),
    OrviboTVCommand("ok", "OK", "310124", "mdi:checkbox-marked-circle-outline"),
    *(
        OrviboTVCommand(str(number), f"Number {number}", f"31010{number}",
                        f"mdi:numeric-{number}-box-outline")
        for number in range(10)
    ),
    OrviboTVCommand("home", "Home", None, "mdi:home"),
    OrviboTVCommand("back", "Back", None, "mdi:arrow-u-left-top"),
    OrviboTVCommand("exit", "Exit", None, "mdi:exit-to-app"),
)
_TV_BY_KEY = {command.key: command for command in TV_COMMANDS}
_TV_BY_ORDER = {command.order: command for command in TV_COMMANDS if command.order}
_LG_NEC_CODES = {
    "power_toggle": 0x20DF10EF, "mute": 0x20DF906F,
    "volume_up": 0x20DF40BF, "volume_down": 0x20DFC03F,
    "channel_up": 0x20DF00FF, "channel_down": 0x20DF807F,
    "menu": 0x20DFC23D, "input": 0x20DFD02F,
    "up": 0x20DF02FD, "down": 0x20DF827D,
    "left": 0x20DFE01F, "right": 0x20DF609F, "ok": 0x20DF22DD,
    "home": 0x20DF3EC1, "back": 0x20DF14EB, "exit": 0x20DFDA25,
    "0": 0x20DF08F7, "1": 0x20DF8877, "2": 0x20DF48B7,
    "3": 0x20DFC837, "4": 0x20DF28D7, "5": 0x20DFA857,
    "6": 0x20DF6897, "7": 0x20DFE817, "8": 0x20DF18E7,
    "9": 0x20DF9867,
}


def is_allone_tv(device: OrviboDevice, devices: Iterable[OrviboDevice]) -> bool:
    """Identify a type-6 TV sharing an Allone Pro's hardware UID."""

    return device.device_type == "6" and bool(device.cloud_uid) and any(
        hub.device_type == "67" and hub.cloud_uid == device.cloud_uid
        for hub in devices
    )


def is_tv_button_order(order: str) -> bool:
    """Recognize only TV button orders recovered from the app."""

    return order in _TV_BY_ORDER


def tv_button_command(action: str) -> OrviboControlCommand:
    """Build a stored TV key command, with its code in order, not value1.

    IrButton.onClick calls control.a.irControl with the layout's command
    string. That overload leaves value1 through value4 at zero.
    """

    if not isinstance(action, str):
        raise ValueError("A TV command must be a command name or known button code")
    description = _TV_BY_KEY.get(action) or _TV_BY_ORDER.get(action)
    if description is None or description.order is None:
        raise ValueError(f"Unsupported TV command: {action}")
    return OrviboControlCommand(description.order, 0)


def tv_commands_for_profile(profile: str) -> tuple[OrviboTVCommand, ...]:
    """Return only keys supported by the explicitly selected TV profile."""

    if profile == "lg":
        return TV_COMMANDS
    if profile == "stored":
        return tuple(command for command in TV_COMMANDS if command.order)
    return ()


def lg_tv_button_command(action: str) -> OrviboControlCommand:
    """Encode a standard LG TV NEC key for the app's raw infrared path.

    The app sends IrData.fre and comma-separated microsecond pulse times
    through alloneControl, core.c.q0, and cmd=15 order='ir control'.
    LG signals are independently captured TV codes; they are not the older
    HomeMate 310xxx stored-key identifiers.
    """

    description = _TV_BY_KEY.get(action) or _TV_BY_ORDER.get(action)
    if description is None or description.key not in _LG_NEC_CODES:
        raise ValueError(f"Unsupported LG TV command: {action}")
    signal = _LG_NEC_CODES[description.key]
    pulses = [8960, 4480]
    for shift in range(31, -1, -1):
        pulses.extend((560, 1680 if signal & (1 << shift) else 560))
    pulses.append(560)
    return OrviboControlCommand(
        "ir control", 0, infrared=OrviboInfrared(38000, tuple(pulses))
    )


def curtain_position_command(ha_position: int) -> OrviboControlCommand:
    """Build a curtain command using the shared 0=closed, 100=open scale."""

    position = max(0, min(100, int(ha_position)))
    return OrviboControlCommand("open", position)


def curtain_stop_command() -> OrviboControlCommand:
    """Build a curtain stop command."""

    return OrviboControlCommand("stop", 0)


def is_rf_curtain(device: OrviboDevice, devices: Iterable[OrviboDevice]) -> bool:
    """Identify a type-34 curtain sharing an Allone hub's hardware UID.

    HomeMate 5.2.5.301 ProductManager.y/E5/F classify RF children by their
    hub UID, including when the hub itself is not selected in HA.
    """

    return device.device_type == "34" and bool(device.cloud_uid) and any(
        hub.device_type in {"30", "67"} and hub.cloud_uid == device.cloud_uid
        for hub in devices
    )


def rf_curtain_command(action: str) -> OrviboControlCommand:
    """Build the type-34 RF button command in HomeMate CurtainCommonActivity.

    D7 supplies these button codes; onActionClick sends the selected code
    unchanged as value1 with order='rf control'. No percentage is encoded.
    """

    codes = {"open": 380000, "close": 380001, "stop": 380002}
    if action not in codes:
        raise ValueError("Unsupported RF curtain action")
    return OrviboControlCommand("rf control", codes[action])


def curtain_position_from_orvibo(value: int | None) -> int | None:
    """Convert a reported ORVIBO curtain position to Home Assistant."""

    if value is None or not 0 <= value <= 100:
        return None
    return value


def light_power_command(
    is_on: bool,
    brightness: int,
    color_temp_kelvin: int,
) -> OrviboControlCommand:
    """Build an active-low light power command."""

    return OrviboControlCommand(
        "on" if is_on else "off",
        0 if is_on else 1,
        _brightness(brightness),
        kelvin_to_mired(color_temp_kelvin),
    )


def power_only_light_command(is_on: bool) -> OrviboControlCommand:
    """Build the captured command used by type-1 and type-102 light relays."""

    return OrviboControlCommand(
        "on" if is_on else "off",
        0 if is_on else 1,
    )


def property_light_power_command(is_on: bool) -> OrviboControlCommand:
    """Build the property command used by type-503 light endpoints."""

    return OrviboControlCommand(
        "set property",
        0,
        properties={"onoff": {"status": "on" if is_on else "off"}},
    )


def light_is_on_from_orvibo(value: int | None) -> bool | None:
    """Interpret the active-low power state used by verified type-38 lights."""

    if value not in (0, 1):
        return None
    return value == 0


def is_supported_tunable_light_profile(
    device_type: str,
    sub_device_type: str,
    model: str,
    brightness: int | None,
    color_temp_mired: int | None,
) -> bool:
    """Return whether a device matches a verified tunable-light profile."""

    if device_type == "503":
        return sub_device_type == "436" and model in _PROPERTY_LIGHT_MODELS
    return device_type == "38" and (
        sub_device_type in _TUNABLE_LIGHT_SUB_DEVICE_TYPES
        and brightness is not None
        and 0 <= brightness <= 255
        and color_temp_mired is not None
        and color_temp_mired > 0
    )


def is_supported_power_only_light_profile(
    device_type: str,
    sub_device_type: str,
) -> bool:
    """Return whether a device matches a verified relay-light profile."""

    return device_type in {"1", "102"} and sub_device_type == "1"


def light_brightness_command(
    brightness: int,
    color_temp_kelvin: int,
) -> OrviboControlCommand:
    """Build a brightness command while preserving color temperature."""

    return OrviboControlCommand(
        "fast move to level",
        0,
        _brightness(brightness),
        max(1, int(color_temp_kelvin)),
    )


def property_light_brightness_command(brightness: int) -> OrviboControlCommand:
    """Build the captured brightness command used by type-503 light endpoints."""

    return OrviboControlCommand(
        "fast move to level",
        0,
        _brightness(brightness),
        0,
    )


def light_color_temp_command(
    brightness: int,
    color_temp_kelvin: int,
) -> OrviboControlCommand:
    """Build a color-temperature command while preserving brightness."""

    return OrviboControlCommand(
        "fast color temperature",
        0,
        _brightness(brightness),
        kelvin_to_mired(color_temp_kelvin),
    )


def kelvin_to_mired(color_temp_kelvin: int) -> int:
    """Convert Kelvin to the integer mired unit used in device status."""

    return round(1_000_000 / max(1, int(color_temp_kelvin)))


def mired_to_kelvin(mired: int) -> int | None:
    """Convert an ORVIBO mired value to Kelvin."""

    return None if mired <= 0 else round(1_000_000 / mired)


def _brightness(value: int) -> int:
    return max(1, min(255, int(value)))
