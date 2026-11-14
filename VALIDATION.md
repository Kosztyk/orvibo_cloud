# Validation — ORVIBO Cloud v1.4.1

## Validation status

This document distinguishes **source tests**, **contributor hardware tests**, **maintainer hardware observations**, and **unverified scenarios**. The production candidate and its release assets were built offline before any GitHub publication. The PR #5 run below does not substitute for new main/tag workflows.

### CI and checks

- `python tools/check_repository.py` (HACS source layout, strings/translation and README sync)
- `python -m unittest discover -s tests -v` (profile controls, swing vectors, Home Assistant stubs, command failures, options wizard, power switch/cleanup, binary/TLS tests when dependencies are installed)
- `python -m compileall -q custom_components`
- On GitHub: `.github/workflows/validate.yml` runs unit/security, HACS and Hassfest; `.github/workflows/release.yml` requires matching stable tag and manifest, validates before publishing a non-prerelease GitHub release.
- PR #5 validation [run 43322696393](https://github.com/Kosztyk/orvibo_cloud/actions/runs/43322696393): **success**, but associated with commit `60f12961...` of the contributor's PR; not a v1.4.1 production CI run.

### Physical hardware evidence

| System | Observed evidence | Limitations |
| --- | --- | --- |
| Vivax/Midea `7579`, Allone Pro | Maintainer exercised mode, temperature, fan and Kaysun/Midea `0xA202FFFFFF7E` swing. Standard `0xA201FFFFFF7C` failed on this unit. | Swing is relative and not physical feedback; other Midea models are not covered. |
| Daikin `10502`, Allone Pro | @matexdj tested v1.4.0b1: Heat 23°C, Off, Cool 19°C, low/high fan, vertical swing/off, Auto, Dry, Fan only, Eco, Comfort. | Tests were on beta b1, not an independent retest of this release. Not every combo captured. |
| BAXI `7404`, Magic Cube | @matexdj tested v1.4.0b1: Heat/Off/Cool, 19–23°C, three fan speeds, vertical/both-axis swing/off, Turbo, Silence, iFeel and Display. OFF and Heat-on 22°C/low fan matched HomeMate scenes exactly (212 durations, 38kHz and command values). Horizontal-only previously moved only horizontal louvers in experimental fork. | No measured iFeel temperature; horizontal-only not independently retested on v1.4.1; no independent cooling/fan captures. |
| Blaupunkt LS 175, Allone Pro | Maintainer confirmed Code 02 Vol+, 03 Vol−, 06 Source, 07 Power toggle, 08 EQ and 10 Mute / BT Pair through this integration. | Physical power status unobservable; codes 01, 04, 05, 09 had no observed response. Switch is optimistic. |
| TV/blinds/lights | Existing maintainer setup previously exercised TV and RF blinds. Existing module implementations and transport were not intentionally changed for v1.4.1. | Carlos's account had no TV, covers or lights; no independent physical regression for those devices in his report. |

### Live Allone Pro unplug/replug test — 2026-11-14 (Europe/Bucharest)

1. With the hub unplugged, a first check saw **ORVIBO Cloud Connection = On**, `Allone Pro.online = true`, `Vivax.online = true`, `Bedroom soundbar.online = true` and Vivax climate `unknown` (available). This demonstrates a cloud-reported online-status delay; it is not a hub-specific ping.
2. Later, with the hub still unplugged, the cloud snapshot reported `online=false` for the hub, Vivax and soundbar; Vivax climate transitioned to **`unavailable` at 01:04:09**.
3. After reconnecting, the hub, Vivax and soundbar returned to `online=true`. Vivax became available again (`unknown`, because physical HVAC state is not reported) at **01:20:09**. The integration remained loaded and cloud discovery successful, without an HA restart or account reauthentication.
4. The actual wall-clock unplug/replug instants were not captured, so **01:04 and 01:20 are HA transition times, not measured detection delays**.

**Disposition:** Keep cloud-connection and hub-status semantics separate. No new speculative offline timeout or active probe is included. Users may observe a delay before cloud-reported hub status changes.

### Software and registration guarantees

- Exact cloud profile IDs and compatible hub routes; no name/model-hash matching for LS175.
- No automatic IR on startup, discovery, refresh or reconnection; commands occur only after explicit user actions.
- Last acknowledged request tracked as assumed climate state; no guarantee of physical HVAC mode, louver position or temperature.
- Entity unique IDs and full configuration flow preserved except intentionally retired beta-only LS175 test controls.
- BAXI four swing outputs are distinct 212-duration/38 kHz frames. Physical directional confirmation for the **current** build remains recommended.
- Daikin encoder behavior is unchanged; conservative LGPL-2.1-only attribution and full license text included.

### Run tests locally

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python tools/check_repository.py
python -m unittest discover -s tests -v
python -m compileall -q custom_components
```

The configured Python version in CI is 3.13. Local `Crypto` import failures mean the binary/TLS test group did not run and must not be counted as passed. The GitHub release workflow installs both `aiohttp` and `pycryptodome` before validation.
