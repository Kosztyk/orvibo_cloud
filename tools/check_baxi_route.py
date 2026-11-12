"""ORVIBO lookup and opt-in BAXI OFF trial outside Home Assistant."""

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

# Load the integration's pure cloud modules without starting Home Assistant.
PACKAGE = "_orvibo_lookup"
package = ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[1] / "custom_components" / "orvibo_cloud")
]
sys.modules[PACKAGE] = package

from _orvibo_lookup.ac_profiles import baxi_7404_candidate
from _orvibo_lookup.api import OrviboCloudClient, OrviboInvalidAuthError, _binary_credentials
from _orvibo_lookup.control import OrviboInfrared
from _orvibo_lookup.protocol import ORVIBO_HOSTS, ac_hub_matches, parse_readtable_devices, password_hash


async def lookup(host: str, email: str, password_md5: str) -> tuple[list[dict], list[tuple]]:
    async with aiohttp.ClientSession() as session:
        client = OrviboCloudClient(session, host=host)
        account = await client.async_discover(email, password_md5)
        result = []
        targets = []
        for family in account.families:
            devices, binary_user, binary_password = await client._async_readtable(
                host, account.access_token, account.user_id, family.family_id
            )
            for device in devices:
                if (device.device_type, device.sub_device_type, device.ir_profile_id) == (
                    "5", "2", "7404"
                ):
                    matches = ac_hub_matches(device, devices)
                    result.append({
                        "profile": "7404",
                        "remote_online": device.online,
                        "hub_matches": matches,
                    })
                    if (
                        device.online is True and device.uid and device.cloud_uid
                        and binary_user and binary_password
                        and any(
                            hub["device_type"] == "30" and hub["same_model"]
                            and hub["same_cloud_uid"] and hub["online"] is True
                            for hub in matches
                        )
                    ):
                        targets.append((
                            host, binary_user, binary_password, family.family_id,
                            device.uid, device.cloud_uid,
                        ))
        return result, targets


def scene_actions(payload: dict, scene_name: str = "BAXI prueba OFF") -> list[list[dict]]:
    """Extract protocol fields from the named manual scene only."""
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return []
    scenes = data.get("scene", [])
    bindings = data.get("sceneBind", [])
    if not isinstance(scenes, list) or not isinstance(bindings, list):
        return []
    result = []
    for scene in scenes:
        if not isinstance(scene, dict) or scene.get("sceneName") != scene_name:
            continue
        number = scene.get("sceneNo")
        if not number or scene.get("delFlag") in (1, "1"):
            continue
        actions = [
            row for row in bindings
            if isinstance(row, dict) and row.get("sceneNo") == number
            and row.get("delFlag") not in (1, "1")
        ]
        result.append(actions)
    return result


def scene_signal(actions: list[dict]) -> dict:
    result = {"actions": len(actions)}
    if len(actions) == 1:
        action, = actions
        result.update(
            ir_control=(action.get("order") or action.get("command")) == "ir control",
            frequency=action.get("freq") if type(action.get("freq")) is int else None,
            pulse_count=action.get("pluseNum") if type(action.get("pluseNum")) is int else None,
            has_pulses=bool(action.get("pluseData")),
        )
    return result


def baxi_scene_command(actions: list[dict], devices: tuple, *, turn_on: bool = False) -> tuple | None:
    """Validate the scene and resolve only its exact online virtual remote."""
    if len(actions) != 1:
        return None
    action, = actions
    remotes = [
        device for device in devices
        if (device.device_type, device.sub_device_type, device.ir_profile_id) == ("5", "2", "7404")
    ]
    if len(remotes) != 1:
        return None
    remote, = remotes
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
        not token.isascii() or not token.isdecimal() or len(token) > 6 for token in tokens
    ):
        return None
    pulses = tuple(map(int, tokens))
    values = tuple(action.get(f"value{i}") for i in range(1, 5))
    if not all(pulses) or any(type(value) is not int for value in values):
        return None
    if turn_on:
        power_and_mode, _, fan, temperature = values
        if power_and_mode & 0x1FF != 2 or fan & 0xFF != 1 or temperature >> 16 != 22:
            return None
    return remote, values, OrviboInfrared(38000, pulses)


async def lookup_scene(
    host: str, email: str, password_md5: str, *, turn_on: bool = False
) -> tuple[list[dict], list[tuple]]:
    """Read the scene and hold a validated command only in memory."""
    async with aiohttp.ClientSession() as session:
        client = OrviboCloudClient(session, host=host)
        account = await client.async_discover(email, password_md5)
        result = []
        targets = []
        for family in account.families:
            payload = await client._async_readtable_payload(
                host, account.access_token, account.user_id, family.family_id
            )
            scene_name = "BAXI prueba ON" if turn_on else "BAXI prueba OFF"
            for actions in scene_actions(payload, scene_name):
                result.append(scene_signal(actions))
                command = baxi_scene_command(
                    actions, parse_readtable_devices(payload), turn_on=turn_on
                )
                user, password = _binary_credentials(payload, account.user_id)
                if command is not None and user and password:
                    remote, values, infrared = command
                    targets.append((
                        host, user, password, family.family_id, remote.uid,
                        remote.cloud_uid, "ir control", *values, None, infrared,
                    ))
        return result, targets


def try_command(
    result: list[dict], targets: list[tuple], save_signal: Path | None = None,
    *, turn_on: bool = False, cool_probe: int | None = None, probe_fan: str = "low", vertical_swing: bool = False,
    horizontal_swing: bool = False,
) -> int:
    """Attempt one validated request after a local physical check."""
    if len(result) != 1 or len(targets) != 1:
        print("La prueba requiere un unico mando 7404 asociado y una orden valida.")
        return 1
    from _orvibo_lookup.binary import control_device

    word = "ENCENDER" if turn_on else "APAGAR"
    if cool_probe is not None:
        word = "FRIO"
        fan_name = {"low": "bajo", "medium": "medio", "high": "alto"}[probe_fan]
        print(f"Prueba experimental: frio a {cool_probe} C con ventilador {fan_name}.")
        if horizontal_swing:
            word = "LAMAS"
            print("Activar oscilacion horizontal, manteniendo la vertical.")
        elif vertical_swing:
            word = "LAMAS"
            print("Activar oscilacion vertical.")
    initial = "apagado" if turn_on else "encendido"
    observed = "encendio" if turn_on else "apago"
    if cool_probe is not None:
        prompt = f"Con el BAXI del salon a la vista, escribe {word} para probar: "
    else:
        prompt = f"Con el BAXI del salon {initial} y a la vista, escribe {word} para probar: "
    confirmation = input(prompt).strip()
    if confirmation != word and not (word == "FRIO" and confirmation == "PROBAR FRIO"):
        print("Prueba cancelada.")
        return 1
    try:
        control_device(*targets[0])
    except Exception:
        print(f"ORVIBO no confirmo la orden. Comprueba si el BAXI se {observed}.")
        return 1
    print(f"ORVIBO respondio a la orden. Comprueba si el BAXI se {observed} fisicamente.")
    if save_signal and input(f"Si viste que se {observed}, escribe CONFIRMADO: ").strip() == "CONFIRMADO":
        signal = targets[0][-1]
        with save_signal.open("x", encoding="utf-8") as file:
            json.dump({
                "profile": "7404",
                "frequency": signal.frequency,
                "pulses": signal.pulses,
                "values": targets[0][7:11],
            }, file, indent=2)
        print("Senal validada guardada en el PC.")
    return 0


_EXTRA_OPTIONS = {
    "1": ("Turbo", "turbo"),
    "2": ("Silence", "silence"),
    "3": ("Display", "display"),
    "4": ("iFeel (solo activacion)", "ifeel"),
    "5": ("Frio de referencia sin opciones", None),
}


def try_extras(result: list[dict], targets: list[tuple]) -> int:
    if len(result) != 1 or len(targets) != 1:
        print("La prueba requiere un unico mando 7404 asociado y una orden valida.")
        return 1
    from _orvibo_lookup.binary import control_device

    print("Todas las pruebas usan frio a 23 C y ventilador medio.")
    while True:
        for number, (label, _) in _EXTRA_OPTIONS.items():
            print(f"{number}. {label}")
        choice = input("Elige una prueba o pulsa Intro para salir: ").strip()
        if not choice:
            return 0
        if choice not in _EXTRA_OPTIONS:
            print("Elige un numero de la lista.")
            continue
        label, extra = _EXTRA_OPTIONS[choice]
        print(f"Prueba seleccionada: {label}.")
        if input("Con el BAXI a la vista, escribe ENVIAR: ").strip() != "ENVIAR":
            print("Prueba cancelada.")
            continue
        cmd = baxi_7404_candidate("cool", 23, "medium", trial_extra=extra)
        try:
            control_device(
                *targets[0][:6], cmd.order, cmd.value1, cmd.value2,
                cmd.value3, cmd.value4, cmd.properties, cmd.infrared,
            )
        except Exception:
            print("ORVIBO no confirmo la orden. Comprueba el equipo.")
        else:
            print("ORVIBO respondio. Comprueba el efecto en el equipo antes de seguir.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--test-off", action="store_true", help="enable the historical OFF trial")
    mode.add_argument("--scene-off", action="store_true", help="inspect the BAXI manual scene")
    mode.add_argument("--scene-test-off", action="store_true", help="try the saved BAXI scene signal")
    mode.add_argument("--scene-test-on", action="store_true", help="try BAXI heat at 22 C, low fan")
    mode.add_argument("--probe-cool", nargs="?", const=24, type=int, choices=range(16, 31), help="try generated BAXI cooling at the chosen Celsius setting")
    mode.add_argument("--probe-extras", action="store_true", help="supervised trial menu for extra buttons")
    parser.add_argument("--probe-fan", choices=("low", "medium", "high"), default="low")
    parser.add_argument("--probe-vertical-swing", action="store_true")
    parser.add_argument("--probe-horizontal-swing", action="store_true")
    parser.add_argument("--save-signal", type=Path, help="save only a physically confirmed signal")
    args = parser.parse_args()
    if (args.probe_fan != "low" or args.probe_vertical_swing or args.probe_horizontal_swing) and args.probe_cool is None:
        parser.error("fan and swing probes require --probe-cool")
    if args.save_signal and not (args.scene_test_off or args.scene_test_on):
        parser.error("--save-signal requires --scene-test-off or --scene-test-on")
    if args.save_signal and args.save_signal.exists():
        parser.error("the signal output file already exists")
    for index, host in enumerate(ORVIBO_HOSTS, start=1):
        print(f"{index}. {host}")
    try:
        while True:
            selection = input("Servidor de ORVIBO Cloud en Home Assistant [2]: ").strip() or "2"
            if selection in {"1", "2", "3", "4"}:
                break
            print("Escribe solo el numero del servidor o pulsa Intro para elegir 2.")
        host = ORVIBO_HOSTS[int(selection) - 1]
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            email = getpass("Correo de HomeMate (oculto): ").strip()
            secret = password_hash(getpass("Contrasena de HomeMate (oculta): "))
        if args.scene_off or args.scene_test_off or args.scene_test_on or args.probe_cool:
            result, targets = asyncio.run(
                lookup_scene(host, email, secret, turn_on=args.scene_test_on)
            )
            print(json.dumps({"baxi_scene": result}, indent=2))
            if args.probe_extras:
                return try_extras(result, targets)
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
                return try_command(
                    result, targets, turn_on=True, cool_probe=args.probe_cool,
                    probe_fan=args.probe_fan,
                    vertical_swing=args.probe_vertical_swing,
                    horizontal_swing=args.probe_horizontal_swing,
                )
            if args.scene_test_off or args.scene_test_on:
                return try_command(
                    result, targets, args.save_signal, turn_on=args.scene_test_on
                )
            return 0
        result, targets = asyncio.run(lookup(host, email, secret))
        print(json.dumps({"remotes": result}, indent=2))
        if args.test_off:
            from _orvibo_lookup.control import STORED_AC_OFF_ORDER
            return try_command(result, [(*target, STORED_AC_OFF_ORDER, 0) for target in targets])
    except OrviboInvalidAuthError:
        print("ORVIBO rechazo el acceso. Revisa servidor y datos de HomeMate.")
        return 1
    except GetPassWarning:
        print("Abre la herramienta en una terminal que permita ocultar los datos.")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nConsulta cancelada.")
        return 1
    except Exception:
        print("La consulta no se completo. Revisa la conexion y el servidor seleccionado.")
        return 1

    if not result:
        print("La cuenta no devolvio ningun mando con el perfil 7404.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
