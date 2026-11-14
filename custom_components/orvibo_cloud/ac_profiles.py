"""Strict HomeMate IR profile registry and protocol-based signal encoders.

Only exact virtual remote IDs are exposed. Protocol-specific functions must
not be applied to an unrelated virtual remote or hub.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from .control import OrviboControlCommand, OrviboInfrared
from .daikin_arc433 import FAN_CODES, HVAC_CODES, daikin_signal
from .midea_48 import MIDEA_FANS, MIDEA_MODES, midea48_signal, midea48_swing_toggle_signal
from .protocol import OrviboDevice


@dataclass(frozen=True, slots=True)
class ACState:
    """Last acknowledged requested state (not physical telemetry)."""
    mode: str | None = None
    temperature: int | None = None
    fan: str | None = None
    swing: str | None = None
    preset: str | None = None
    previous_mode: str | None = None


@dataclass(frozen=True, slots=True)
class ACProfile:
    """Supported capabilities and signal encoder for one exact cloud profile."""
    manufacturer: str
    remote: str
    default: ACState
    modes: tuple[str, ...]
    encode: Callable[[ACState], OrviboControlCommand]
    hub_type: str = "67"
    turn_on_mode: str | None = None
    temperatures: range | None = None
    fans: tuple[str, ...] = ()
    swings: tuple[str, ...] = ()
    presets: tuple[str, ...] = ()
    momentary_presets: tuple[str, ...] = ()
    remember_settings: bool = False
    # Midea swing is a separate toggle. Normal Midea frames do not set swing.
    swing_toggle_encoder: Callable[[], OrviboControlCommand] | None = None
    mode_defaults: Mapping[str, ACState] = field(default_factory=dict)

    def command(self, state: ACState) -> OrviboControlCommand:
        if state.mode not in self.modes:
            raise ValueError("Unsupported AC mode")
        if state.temperature is not None and (
            self.temperatures is None or type(state.temperature) is not int
            or state.temperature not in self.temperatures
        ):
            raise ValueError("Unsupported AC target temperature")
        if state.fan is not None and state.fan not in self.fans:
            raise ValueError("Unsupported AC fan mode")
        if state.swing is not None and state.swing not in self.swings:
            raise ValueError("Unsupported AC swing mode")
        if state.preset is not None and state.preset not in self.presets:
            raise ValueError("Unsupported AC preset")
        return self.encode(state)


def _daikin_10502_command(state: ACState) -> OrviboControlCommand:
    """Generate full Daikin state from the ARC433-compatible IR pattern."""
    powered = state.mode != "off"
    mode = state.mode if powered else state.previous_mode
    signal = daikin_signal(
        power=powered,
        mode=mode or "heat",
        temperature=state.temperature if state.temperature is not None else 23,
        fan=state.fan or "auto",
        eco=state.preset in ("eco", "eco_comfort"),
        comfort=state.preset in ("comfort", "eco_comfort"),
        swing_v=state.swing == "vertical",
    )
    return OrviboControlCommand(
        "ir control", 0, infrared=OrviboInfrared(signal.frequency, signal.pulses)
    )


# Exact 212-duration BAXI OFF scene. Signal only; no household identifiers.
_BAXI_7404_OFF_PULSES = (
    9000, 4500, 560, 1680, 560, 1680, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 1680, 560, 1680, 560, 1680, 560, 1680, 560, 1680,
    560, 560, 560, 1680, 560, 1680, 560, 1680, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 560, 560, 560, 560, 1680, 560, 1680,
    560, 1680, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 1680, 560, 1680, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 1680, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 560, 1680,
    560, 560, 560, 1680, 560, 560, 560, 560, 560, 560, 560, 560,
    560, 560, 560, 1680, 560, 1680, 560, 1680, 560, 1680, 560, 1680,
    560, 1680, 560, 1680, 560, 1680, 560, 1000,
)


_BAXI_MODE_DEFAULTS = {
    "heat": ACState("heat", 22, "low", "off", "none"),
    "cool": ACState("cool", 19, "low", "off", "none"),
}


def baxi_7404_candidate(
    mode: str, temperature: int, fan: str, *,
    vertical_swing: bool = False, horizontal_swing: bool = False,
    trial_extra: str | None = None,
) -> OrviboControlCommand:
    """Generate a 13-byte Electra/AUX-style frame from observed BAXI scene data."""
    if mode not in ("heat", "cool") or fan not in ("low", "medium", "high"):
        raise ValueError("Unsupported BAXI operating mode or fan")
    if type(temperature) is not int or not 16 <= temperature <= 30:
        raise ValueError("Unsupported BAXI trial temperature")
    frame = bytearray.fromhex("c3 77 e0 00 60 00 80 00 00 30 00 05 2f")
    fan_code = {"low": 1, "medium": 2, "high": 3}[fan]
    direction = 0 if vertical_swing else 1
    swing_bits = 0 if vertical_swing else 7
    frame[1] = ((temperature - 8) << 3) | swing_bits
    if horizontal_swing:
        frame[2] &= 31
    frame[4] = (frame[4] & 31) | ((4 - fan_code) << 5)
    frame[6] = (frame[6] & 31) | ((4 if mode == "heat" else 1) << 5)
    if trial_extra == "turbo":
        frame[5] |= 0x40
    elif trial_extra == "silence":
        frame[5] |= 0x80
    elif trial_extra == "display":
        frame[11] |= 0x10
    elif trial_extra == "ifeel":
        frame[6] |= 0x08
    elif trial_extra is not None:
        raise ValueError("Unsupported BAXI extra")
    frame[-1] = sum(frame[:-1]) & 255
    pulses = [9000, 4500]
    for byte in frame:
        for bit in range(8):
            pulses.extend((560, 1680 if byte & (1 << bit) else 560))
    pulses.extend((560, 1000))
    state_mode, scene_mode = (1, 4) if mode == "heat" else (0, 1)
    scene_key = 200000 + scene_mode * 10000 + fan_code * 1000 + direction * 100 + temperature
    return OrviboControlCommand(
        "ir control", state_mode << 1, scene_key, (direction << 8) | fan_code,
        (temperature << 16) | (136 << 8),
        infrared=OrviboInfrared(38000, tuple(pulses)),
    )


def _baxi_7404_command(state: ACState) -> OrviboControlCommand:
    """Use verified OFF capture or encode an Electra-compatible AC command."""
    if state.mode == "off":
        return OrviboControlCommand(
            "ir control", 3, 141122, 257, 1476608,
            infrared=OrviboInfrared(38000, _BAXI_7404_OFF_PULSES),
        )
    if state.mode in ("heat", "cool"):
        defaults = _BAXI_MODE_DEFAULTS[state.mode]
        return baxi_7404_candidate(
            state.mode,
            state.temperature if state.temperature is not None else defaults.temperature,
            state.fan or defaults.fan,
            vertical_swing=state.swing in ("vertical", "both"),
            horizontal_swing=state.swing in ("horizontal", "both"),
            trial_extra=state.preset if state.preset not in (None, "none") else None,
        )
    raise ValueError("Unsupported BAXI operating state")


def _midea_7579_command(state: ACState) -> OrviboControlCommand:
    """Generate Midea 48-bit full-state IR for verified Vivax profile 7579.

    Only the exact cloud IR profile and compatible Allone Pro route qualify.
    No HomeMate scenes are required.
    """
    powered = state.mode != "off"
    mode = state.mode if powered else (state.previous_mode or "cool")
    signal = midea48_signal(
        power=powered, mode=mode or "cool",
        temperature=state.temperature if state.temperature is not None else 23,
        fan=state.fan or "auto",
    )
    return OrviboControlCommand(
        "ir control", 0, infrared=OrviboInfrared(signal.frequency, signal.pulses)
    )


def _midea_7579_swing_toggle() -> OrviboControlCommand:
    signal = midea48_swing_toggle_signal()
    return OrviboControlCommand(
        "ir control", 0, infrared=OrviboInfrared(signal.frequency, signal.pulses)
    )


IR_PROFILES = {
    ("5", "2", "10502"): ACProfile(
        manufacturer="Daikin", remote="ARC433A87",
        default=ACState(temperature=23, fan="auto", swing="off", preset="none"),
        modes=("off", *HVAC_CODES), encode=_daikin_10502_command,
        turn_on_mode="heat", temperatures=range(16, 31), fans=tuple(FAN_CODES),
        swings=("off", "vertical"),
        presets=("none", "eco", "comfort", "eco_comfort"),
        remember_settings=True,
    ),
    ("5", "2", "7579"): ACProfile(
        manufacturer="Vivax / Midea", remote="Midea 48-bit",
        default=ACState(temperature=23, fan="auto"),
        modes=("off", "cool", "heat", "auto", "dry", "fan_only"),
        encode=_midea_7579_command, hub_type="67", turn_on_mode="cool",
        temperatures=range(17, 31), fans=tuple(MIDEA_FANS),
        swings=("off", "vertical"),
        remember_settings=True,
        swing_toggle_encoder=_midea_7579_swing_toggle,
    ),
    ("5", "2", "7404"): ACProfile(
        manufacturer="BAXI", remote="Anori JSG35", default=ACState(),
        modes=("off", "heat", "cool"), encode=_baxi_7404_command,
        hub_type="30", turn_on_mode="heat", temperatures=range(19, 24),
        fans=("low", "medium", "high"),
        # Horizontal-only was physically exercised on BAXI in the contributor's
        # experimental fork; the public profile exposes horizontal-only swing.
        swings=("off", "vertical", "horizontal", "both"),
        presets=("none", "turbo", "silence", "ifeel", "display"),
        momentary_presets=("display",), mode_defaults=_BAXI_MODE_DEFAULTS,
    ),
}


def ac_profile(device: OrviboDevice) -> ACProfile | None:
    """Match by exact device type, subtype and numeric HomeMate profile ID."""
    return IR_PROFILES.get((device.device_type, device.sub_device_type, device.ir_profile_id))
