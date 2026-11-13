#!/usr/bin/env python3
"""Opt-in BAXI cloud route diagnostics and supervised physical IR tests.

Usage: python tools/check_baxi_route.py [--scene-off|--scene-test-off|
        --scene-test-on|--probe-cool 23|--probe-extras]

Read-only by default. No raw identifiers, credentials or signal dumps are printed.
A physical IR request always requires an explicit confirmation at the keyboard.
"""
from __future__ import annotations

import argparse
import asyncio
from getpass import GetPassWarning, getpass
import json
from pathlib import Path
import sys
from types import ModuleType
import warnings

import aiohttp

PACKAGE = "_orvibo_lookup"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components" / "orvibo_cloud")]
sys.modules[PACKAGE] = package

from _orvibo_lookup.ac_profiles import baxi_7404_candidate  # noqa: E402
from _orvibo_lookup.api import OrviboCloudClient, OrviboInvalidAuthError, _binary_credentials  # noqa: E402
from _orvibo_lookup.control import OrviboInfrared  # noqa: E402
from _orvibo_lookup.protocol import ac_hub_matches, parse_readtable_devices, password_hash  # noqa: E402

ORVIBO_HOSTS = (
    "china.orvibo.com", "homemate.orvibo.com",
    "germany.orvibo.com", "usa.orvibo.com",
)


def scene_actions(payload: dict, scene_name: str) -> list[list[dict]]:
    """Extract action lists for one named user-created HomeMate scene."""
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return []
    scenes, binds = data.get("scene", []), data.get("sceneBind", [])
    if not isinstance(scenes, list) or not isinstance(binds, list):
        return []
    result = []
    for scene in scenes:
        if not isinstance(scene, dict) or scene.get("sceneName") != scene_name:
            continue
        scene_no = scene.get("sceneNo")
        if not scene_no or scene.get("delFlag") in (1, "1"):
            continue
        result.append([
            action for action in binds
            if isinstance(action, dict) and action.get("sceneNo") == scene_no
            and action.get("delFlag") not in (1, "1")
        ])
    return result


def scene_signal(actions: list[dict]) -> dict:
    """Report only non-sensitive metadata for a scene's IR frame."""
    result = {"actions": len(actions)}
    if len(actions) == 1:
        action = actions[0]
        result.update(
            ir_control=(action.get("order") or action.get("command")) == "ir control",
            frequency=action.get("freq") if type(action.get("freq")) is int else None,
            pulse_count=action.get("pluseNum") if type(action.get("pluseNum")) is int else None,
            has_pulses=bool(action.get("pluseData")),
        )
    return result


def baxi_scene_command(actions: list[dict], devices: tuple, *, turn_on: bool = False) -> tuple | None:
    """Fail closed unless exactly one valid online BAXI virtual remote matches."""
    if len(actions) != 1:
        return None
    action = actions[0]
    remotes = [
        d for d in devices
        if (d.device_type, d.sub_device_type, d.ir_profile_id) == ("5", "2", "7404")
    ]
    if len(remotes) != 1:
        return None
    remote = remotes[0]
    if (
        not remote.uid or not remote.cloud_uid or remote.online is not True
        or not any(
            match["device_type"] == "30" and match["same_cloud_uid"]
            and match["same_model"] and match["online"] is True
            for match in ac_hub_matches(remote, devices)
        )
        or action.get("deviceId") != remote.uid
        or action.get("uid") not in (None, "", remote.cloud_uid)
        or (action.get("order") or action.get("command")) != "ir control"
        or action.get("freq") != 38000 or action.get("pluseNum") != 212
    ):
        return None
    raw = action.get("pluseData")
    if not isinstance(raw, str) or len(raw) > 4096:
        return None
    tokens = raw.split(",")
    if len(tokens) != 212 or any(
        not token.isascii() or not token.isdecimal() or len(token) > 6
        for token in tokens
    ):
        return None
    pulses = tuple(map(int, tokens))
    values = tuple(action.get(f"value{i}") for i in range(1, 5))
    if not all(pulses) or any(type(value) is not int for value in values):
        return None
    if turn_on:
        value1, _, fan, temperature = values
        if value1 & 0x1FF != 2 or fan & 0xFF != 1 or temperature >> 16 != 22:
            return None
    return remote, values, OrviboInfrared(38000, pulses)


async def lookup(host: str, email: str, password_md5: str, *, scene: str | None = None, turn_on: bool = False) -> tuple[list[dict], list[tuple]]:
    """Discover devices or validated scene data over current HTTPS endpoint."""
    async with aiohttp.ClientSession() as session:
        client = OrviboCloudClient(session, host=host)
        account = await client.async_discover(email, password_md5)
        info, targets = [], []
        for family in account.families:
            payload = await client._async_readtable_payload(
                host, account.access_token, account.user_id, family.family_id
            )
            devices = parse_readtable_devices(payload)
            binary_user, binary_password = _binary_credentials(payload, account.user_id)
            if scene is None:
                for device in devices:
                    if (device.device_type, device.sub_device_type, device.ir_profile_id) != ("5", "2", "7404"):
                        continue
                    info.append({
                        "profile": "7404", "remote_online": device.online,
                        "hub_matches": ac_hub_matches(device, devices),
                    })
                continue
            for actions in scene_actions(payload, scene):
                info.append({"scene": scene, **scene_signal(actions)})
                command = baxi_scene_command(actions, devices, turn_on=turn_on)
                if command is None or not binary_user or not binary_password:
                    continue
                remote, values, infrared = command
                targets.append((
                    host, binary_user, binary_password, family.family_id,
                    remote.uid, remote.cloud_uid, "ir control", *values,
                    None, infrared,
                ))
        return info, targets


def send_once(targets: list[tuple], *, label: str, save_signal: Path | None = None) -> int:
    """Require a single target, explicit keyboard opt-in, and no automatic retries."""
    if len(targets) != 1:
        print("Exactly one valid matched remote is required; nothing sent.")
        return 1
    print(f"Experimental physical IR test: {label}. Keep the AC in view.")
    if input("Type SEND to transmit ONE command: ").strip() != "SEND":
        print("Cancelled; no IR command sent.")
        return 1
    from _orvibo_lookup.binary import control_device
    try:
        control_device(*targets[0])
    except Exception:
        print("ORVIBO did not acknowledge the command; physical result unknown.")
        return 1
    print("Cloud acknowledged the command; verify actual AC behavior yourself.")
    if save_signal and input("If physically verified, type CONFIRMED to save signal: ").strip() == "CONFIRMED":
        signal = targets[0][-1]
        with save_signal.open("x", encoding="utf-8") as out:
            json.dump({
                "profile": "7404", "frequency": signal.frequency,
                "pulses": signal.pulses, "values": targets[0][7:11],
            }, out, indent=2)
        print("Saved protocol fields only. Review the output before sharing.")
    return 0


_EXTRAS = {
    "1": ("Turbo", "turbo"),
    "2": ("Silence", "silence"),
    "3": ("Display toggle", "display"),
    "4": ("iFeel (no remote temperature uplink)", "ifeel"),
    "5": ("No extra (baseline)", None),
}


def try_extras(targets: list[tuple]) -> int:
    """Run explicit single-command tests of individual BAXI extras."""
    if len(targets) != 1:
        print("Exactly one BAXI scene and remote required; nothing sent.")
        return 1
    while True:
        for key, (label, _) in _EXTRAS.items():
            print(f"{key}. {label}")
        choice = input("Choose a control or Enter to exit: ").strip()
        if not choice:
            return 0
        if choice not in _EXTRAS:
            print("Invalid selection")
            continue
        label, extra = _EXTRAS[choice]
        command = baxi_7404_candidate("cool", 23, "medium", trial_extra=extra)
        target = (*targets[0][:6], command.order, command.value1,
                  command.value2, command.value3, command.value4,
                  command.properties, command.infrared)
        send_once([target], label=label)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--scene-off", action="store_true", help="read-only OFF scene metadata")
    mode.add_argument("--scene-test-off", action="store_true", help="supervised OFF scene command")
    mode.add_argument("--scene-test-on", action="store_true", help="supervised heat ON scene command")
    mode.add_argument("--probe-cool", nargs="?", const=23, type=int, choices=range(19,24), help="supervised COOL test at 19-23 C")
    mode.add_argument("--probe-extras", action="store_true", help="supervised extra controls menu")
    parser.add_argument("--probe-fan", choices=("low", "medium", "high"), default="low")
    parser.add_argument("--probe-vertical-swing", action="store_true")
    parser.add_argument("--probe-horizontal-swing", action="store_true", help="not exposed in climate; physical test only")
    parser.add_argument("--save-signal", type=Path, help="write confirmed scene signal to local file")
    return parser


def wants_scene_lookup(args: argparse.Namespace) -> bool:
    """Explicit helper for CLI tests; --probe-extras must enter scene lookup."""
    return bool(
        args.scene_off or args.scene_test_off or args.scene_test_on
        or args.probe_cool is not None or args.probe_extras
    )


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    if (args.probe_fan != "low" or args.probe_vertical_swing or args.probe_horizontal_swing) and args.probe_cool is None:
        parser.error("fan and swing flags require --probe-cool")
    if args.save_signal and not (args.scene_test_on or args.scene_test_off):
        parser.error("--save-signal requires --scene-test-on/off")
    if args.save_signal and args.save_signal.exists():
        parser.error("signal output path already exists")
    for index, host in enumerate(ORVIBO_HOSTS, start=1):
        print(f"{index}. {host}")
    try:
        while True:
            selection = input("HomeMate server [2]: ").strip() or "2"
            if selection in ("1", "2", "3", "4"):
                break
            print("Select 1 through 4")
        host = ORVIBO_HOSTS[int(selection) - 1]
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            email = getpass("HomeMate email (hidden): ").strip()
            hashed = password_hash(getpass("HomeMate password (hidden): "))
        if wants_scene_lookup(args):
            scene = "BAXI prueba ON" if args.scene_test_on else "BAXI prueba OFF"
            info, targets = asyncio.run(lookup(host, email, hashed, scene=scene, turn_on=args.scene_test_on))
            print(json.dumps({"baxi_scene": info}, indent=2))
            if args.scene_off:
                return 0
            if args.probe_extras:
                return try_extras(targets)
            if args.probe_cool is not None:
                command = baxi_7404_candidate(
                    "cool", args.probe_cool, args.probe_fan,
                    vertical_swing=args.probe_vertical_swing,
                    horizontal_swing=args.probe_horizontal_swing,
                )
                targets = [
                    (*target[:6], command.order, command.value1, command.value2,
                     command.value3, command.value4, command.properties, command.infrared)
                    for target in targets
                ]
                return send_once(targets, label=f"cool {args.probe_cool}C / {args.probe_fan}")
            return send_once(targets, label="BAXI ON" if args.scene_test_on else "BAXI OFF", save_signal=args.save_signal)
        info, _ = asyncio.run(lookup(host, email, hashed))
        print(json.dumps({"remotes": info}, indent=2))
        return 0
    except OrviboInvalidAuthError:
        print("ORVIBO rejected credentials or region selection.")
    except GetPassWarning:
        print("Open a real terminal that supports hidden password entry.")
    except (EOFError, KeyboardInterrupt):
        print("Cancelled")
    except Exception:
        print("Diagnostic failed. Verify network and selected server.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
