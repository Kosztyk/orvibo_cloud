> **Distribution withdrawal — 19 November 2026**
>
> Vendor TLS client credentials have been removed from this source. Affected releases and historical copies are being withdrawn following ORVIBO's reported refusal to authorize redistribution of those credentials. The current binary cloud transport requires the removed credentials, so clean installations cannot use that transport. The climate encoders, device profiles and test records remain available for continued development. Cleanup coordination is tracked in [issue #6](https://github.com/Kosztyk/orvibo_cloud/issues/6).

<img width="512" height="512" alt="ORVIBO Cloud" src="https://github.com/user-attachments/assets/10a03183-279c-44c6-9bff-c0eaab6959f2" />

# ORVIBO Cloud for Home Assistant

A native Home Assistant integration for **ORVIBO Cloud / HomeMate**, including RF blinds, virtual TV remotes, selected native IR climate remotes and an opt-in Blaupunkt LS 175 soundbar profile.

**ORVIBO Cloud v1.4.2** · [Release notes](https://github.com/Kosztyk/orvibo_cloud/blob/main/RELEASE_NOTES_1.4.2.md) · [Changelog](https://github.com/Kosztyk/orvibo_cloud/blob/main/CHANGELOG.md) · [Validation](https://github.com/Kosztyk/orvibo_cloud/blob/main/VALIDATION.md) · [Publishing](https://github.com/Kosztyk/orvibo_cloud/blob/main/HACS_PUBLISHING.md)

## What's new in v1.4.2

- BAXI Anori JSG35 profile `7404` offers **16–32 °C** in Heat and Cool. The expanded range has offline encoder coverage. Physical testing of commands from Home Assistant covered 19–23 °C.
- Device controls wait for a matching cloud acknowledgement before updating assumed state. RF-blind Stop adds a **Stopped** entry to Activity.
- The LS 175 Power switch serializes state checks and IR toggles. TV sequences accept up to 40 keys including repeats, with AC and soundbar controls able to run between keys.
- Door sensors favor the freshest observation and request a fresh snapshot after reconnect. A malformed device table keeps the last successful snapshot.
- The integration verifies the binary server automatically using HomeMate's bundled CA, refuses the shared client key as a server key, rejects REST redirects and minimizes identifying information in diagnostics.

## Features

- **RF blinds:** Open, Close and Stop for compatible Allone/Allone Pro devices, with optional persistent **assumed** state and expiration. No measured position is claimed.
- **TV remotes:** Home Assistant `remote` entities and command buttons for supported virtual TV remotes.
- **Air-conditioning:** Exact-profile native IR `climate` entities; no HomeMate scenes required for ordinary control.
- **Blaupunkt LS 175:** Opt-in HomeMate type-7/subtype-0 speaker profile via a compatible Allone Pro, with five confirmed momentary command buttons and a Power **switch**.
- **Diagnostics:** Authenticated ORVIBO cloud connection, discovered device count, privacy-redacted diagnostics and optional raw event capture.
- **Security:** Binary mutual TLS verifies the CA and hostname, then checks the server public key before login. The REST client rejects redirects.

## Supported IR climate profiles

| HomeMate virtual AC | Profile ID | Hub | Available features |
| --- | --- | --- | --- |
| Daikin ARC433A87-compatible | `10502` | Allone Pro (`67`) | Off / Auto / Cool / Heat / Dry / Fan only; 16–30 °C; Auto / Low / Medium / High fan; vertical swing; Eco / Comfort |
| BAXI Anori JSG35 | `7404` | Magic Cube (`30`) | Off / Cool / Heat, 16–32 °C (19–23 °C tested on hardware), Low / Medium / High fan, Off / Vertical / Horizontal / Both swing, Turbo / Silence / iFeel / Display |
| Vivax / Midea 48-bit | `7579` | Allone Pro (`67`) | Off / Auto / Cool / Heat / Dry / Fan only; 17–30 °C; Auto / Low / Medium / High fan; tested Kaysun-compatible vertical swing toggle |

AC devices are matched by exact HomeMate virtual remote type `5`, subtype `2`, numeric profile ID and a compatible discovered hub. Merely naming a remote “Daikin”, “BAXI” or “Vivax” is not sufficient.

Carlos (@matexdj) verified horizontal-only louver movement on `v1.4.1b9` and observed 16–32 °C on the original BAXI remote. Offline tests check the expanded Home Assistant range and all four swing modes. The iFeel preset is an IR command and Display is momentary. [BAXI validation guide](https://github.com/Kosztyk/orvibo_cloud/blob/main/BAXI_VALIDATION_GUIDE.md)

**Daikin:** Contributor hardware testing on the v1.4.0b1 candidate confirmed Heat, Cool, Off, Auto, Dry, Fan only, low/high fan, vertical swing, Eco and Comfort. Not every possible combination has been independently captured. The Daikin encoder retains its validated OFF signal and existing waveform logic.

**Vivax:** The maintainer physically confirmed Midea 48-bit mode/temperature/fan commands and the alternative Kaysun/Midea swing packet `0xA202FFFFFF7E`; the standard `0xA201FFFFFF7C` did not actuate this unit. Swing is a **relative toggle**; state may diverge after controlling the AC outside Home Assistant. The Kaysun packet is restricted to this profile and must not be used for arbitrary Midea devices.

### Climate state and availability

IR command acknowledgement means ORVIBO accepted the cloud request, **not** that the AC reached a physical mode or temperature. Climate state is the last acknowledged request and starts `unknown` after restart/reload. Setup, polling and reconnect do not automatically emit infrared signals.

Climate availability requires a successful cloud refresh and a compatible cloud-reported online hub route. The cloud may **temporarily cache a hub as online after disconnection**. During a live Allone Pro unplug/replug test on 14 November 2026, its cloud `online` flag eventually became `false`, Vivax became `unavailable`, and both recovered without restart after reconnection. `binary_sensor.orvibo_cloud_connection` correctly remained **On**, because it measures the cloud API, not an individual hub. The exact cloud-side detection delay has not been established; there is no intrusive heartbeat probe or automatic IR test. See [VALIDATION.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/VALIDATION.md).

## Other supported HomeMate devices

| Device | HomeMate match | Controls |
| --- | --- | --- |
| RF blind or curtain | Type `34`, matching Magic Cube (`30`) or AllOne Pro (`67`) | Open, Close, Stop and optional remembered state |
| Position-capable curtain motor | Supported type `34` motor with position control | Open, Close, Stop and position |
| Virtual TV remote | Type `6`, matching AllOne Pro (`67`) | TV remote and buttons using the configured LG or stored-profile keys |
| Blaupunkt LS 175 virtual speaker | Type `7`, subtype `0`, matching AllOne Pro (`67`) and per-device model opt-in | Power toggle, volume, source, equalizer, mute and Bluetooth pairing |
| Supported lights and relays | Tunable type `38` and selected `503` profiles, or relay type `1` or `102` with subtype `1` | On/Off, with brightness and color temperature on supported tunable models |
| Door status | Selected HomeMate device exposes the `door_status` property | Open/closed binary sensor using polling and push observations |

## Blaupunkt LS 175 soundbar

An existing HomeMate virtual speaker must be type `7`, subtype `0`, selected for this integration and associated with one compatible Allone Pro hub. In **ORVIBO Cloud → Configure**, complete the **entire existing options wizard** (cloud/TV/diagnostics → device selection → per-device area and RF settings). On the speaker's page choose **Speaker infrared model → Blaupunkt LS 175**; the default is None. Do not infer the profile from a speaker name or hardcode a model hash.

| Home Assistant control | Confirmed 38-kHz NEC code | Behavior |
| --- | --- | --- |
| **Power** (`switch`) | `0x00FFA25D` (Code 07) | Physical power **toggle** |
| **Vol +** (`button`) | `0x00FFA857` (Code 02) | Volume up |
| **Vol −** (`button`) | `0x00FF18E7` (Code 03) | Volume down |
| **Source** (`button`) | `0x00FFE21D` (Code 06) | Change input source |
| **Equalizer** (`button`) | `0x00FF38C7` (Code 08) | EQ selection |
| **Mute / BT Pair** (`button`) | `0x00FF5AA5` (Code 10) | Mute; Bluetooth pairing in the appropriate mode |

The soundbar provides no actual power telemetry and no separate power-on/power-off infrared codes. The Power switch tracks a **local optimistic estimate**; it may be out of sync after use of the original remote, HomeMate or a power outage. `switch.toggle` always sends one Code 07 command; `turn_on` and `turn_off` use the local estimate and do not guarantee the soundbar's physical state. No infrared commands run at startup. Code 01, 04, 05 and 09 were not observed to work; they are retained in the offline mapping but not exposed as normal entities.

The former beta-only LS175 IR test remote, unused test buttons and momentary Power button are retired; the integration prunes **only their obsolete, integration-owned registry entries**. The other five button unique IDs remain unchanged across the betas. An automation that referenced the removed Power *button* needs to target the new Power *switch*. See [LS175_GUIDE.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/LS175_GUIDE.md).

## Installation and upgrades

### HACS (recommended)

In HACS, search for **ORVIBO Cloud**, choose **Download** or **Update** to `1.4.2`, and restart Home Assistant. New installations can then add ORVIBO Cloud under **Settings → Devices & services**. [HACS default catalog entry](https://github.com/hacs/default/pull/12441)

### Manual installation

Back up `/config/custom_components/orvibo_cloud`. Extract the installation ZIP into `/config`, or copy `custom_components/orvibo_cloud` from the GitHub source archive into `/config/custom_components`. Replace the integration directory as a unit and restart Home Assistant. Existing configuration entries, device selections and entity IDs carry over. [GitHub releases](https://github.com/Kosztyk/orvibo_cloud/releases)

To enable a virtual AC or speaker, go to **Settings → Devices & services → ORVIBO Cloud → Configure**, select the device and complete all remaining options pages. The cloud/TV settings, device selection, per-device areas and RF-blind remember/restore/expiry settings are preserved. A matching physical hub need not be explicitly selected as a separate entity.

## Cloud login and servers

Choose the server associated with the HomeMate account: `homemate.orvibo.com`, `germany.orvibo.com`, `china.orvibo.com` or `usa.orvibo.com`. Account affinity may differ from physical location. Do not disable certificate or hostname verification when troubleshooting. Secrets and household identifiers should be redacted before sharing diagnostics.

### Automatic binary server verification

After the normal update and restart, ORVIBO Cloud uses the bundled HomeMate CA automatically. Existing accounts and device selections carry over. Each connection to port `10002` checks the certificate chain and hostname and rejects the publicly distributed HomeMate client key before sending binary protocol data.

Diagnostics show `vendor_ca` as the `binary_server_trust` setting by default. An existing verified `/config/orvibo_trust/<hostname>.spki` file adds a public-key restriction and reports `pin_configured`. These values describe the configured verification policy. The peer is verified on each connection.

The push listener starts when a selected device exposes door events or raw event capture is enabled. A server identity failure stops the listener until reload.

## RF blind assumed-state options

Where supported, the per-blind device settings include **Remember assumed state**, **Restore after restart** and an optional expiry in whole minutes (`0` disables expiry). A successful Open or Close can store an assumed end state. Stop clears the position assumption and adds a **Stopped** command entry to Activity. Home Assistant may also record **Unknown** as the cover's position state. Failed commands leave the last successful action intact.

## Diagnostics and troubleshooting

The cloud connection binary sensor reports whether the last authenticated coordinator refresh succeeded. It is **not** a hub ping. Cloud snapshots provide the individual hub/remote `online` flags; their freshness depends on ORVIBO. The discovered-device sensor provides a count and sanitized device-type information. Optional raw event capture is diagnostic and may reconnect periodically; it does not intercept phone-app IR commands.

If an AC is unavailable, check the selected virtual remote, its profile ID, a matching compatible hub, and the hub's cloud-reported `online` flag. If a speaker control is unavailable, confirm that the soundbar's device page has the Blaupunkt model selected and that the hub route is online. Do not enable unsupported models merely because their IR format looks similar.

An acknowledgement timeout leaves the physical command outcome unknown, even while cloud discovery works. Soundbar and AC requests share a lock. Several quick presses can queue behind a command waiting for a reply.

## Validation, credits and licensing

See [VALIDATION.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/VALIDATION.md) for the precise hardware-test scope, acknowledged gaps, test commands and historical PR CI link. The documented HA 2026.11.1 tests do not prove every model/firmware combination; untested physical controls remain qualified.

Maintained by [@Kosztyk](https://github.com/Kosztyk), based on [maycode0-0/orvibo-cloud](https://github.com/maycode0-0/orvibo-cloud). Daikin and BAXI work builds on Carlos [@matexdj](https://github.com/matexdj)'s [PR #5](https://github.com/Kosztyk/orvibo_cloud/pull/5). The RF blind remembered-state feature follows an idea from @craiglemon ([PR #2](https://github.com/Kosztyk/orvibo_cloud/pull/2)).

The repository retains its MIT-licensed original components, while the Daikin encoder is **specifically marked LGPL-2.1-only** with upstream copyright attribution because matching IRremoteESP8266 reset-state constants make independent authorship uncertain. The full LGPL text is distributed in `LICENSES/LGPL-2.1.txt` and inside the integration ZIP. See [THIRD_PARTY_NOTICES.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/THIRD_PARTY_NOTICES.md) and [PROVENANCE_AUDIT.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/PROVENANCE_AUDIT.md). This is a conservative file-specific license disposition, not a legal opinion certifying complete clean-room provenance.
