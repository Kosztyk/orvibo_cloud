<img width="512" height="512" alt="ORVIBO Cloud" src="https://github.com/user-attachments/assets/10a03183-279c-44c6-9bff-c0eaab6959f2" />

# ORVIBO Cloud for Home Assistant

A native Home Assistant integration for **ORVIBO Cloud / HomeMate**, including RF blinds, virtual TV remotes, selected native IR climate remotes and an opt-in Blaupunkt LS 175 soundbar profile.

**Latest stable release: v1.4.1** · [Release notes](https://github.com/Kosztyk/orvibo_cloud/blob/main/RELEASE_NOTES_1.4.1.md) · [Changelog](https://github.com/Kosztyk/orvibo_cloud/blob/main/CHANGELOG.md) · [Validation](https://github.com/Kosztyk/orvibo_cloud/blob/main/VALIDATION.md) · [Publishing](https://github.com/Kosztyk/orvibo_cloud/blob/main/HACS_PUBLISHING.md)

## Features

- **RF blinds:** Open, Close and Stop for compatible Allone/Allone Pro devices, with optional persistent **assumed** state and expiration. No measured position is claimed.
- **TV remotes:** Home Assistant `remote` entities and command buttons for supported virtual TV remotes.
- **Air-conditioning:** Exact-profile native IR `climate` entities; no HomeMate scenes required for ordinary control.
- **Blaupunkt LS 175:** Opt-in HomeMate type-7/subtype-0 speaker profile via a compatible Allone Pro, with five confirmed momentary command buttons and a Power **switch**.
- **Diagnostics:** Authenticated ORVIBO cloud connection, discovered device count, privacy-redacted diagnostics and optional raw event capture.
- **Security:** Reuses the verified binary mutual-TLS client, pinned CA, hostname verification and unchanged transport from v1.4.0.

## Supported IR climate profiles

| HomeMate virtual AC | Profile ID | Hub | Available features |
| --- | --- | --- | --- |
| Daikin ARC433A87-compatible | `10502` | Allone Pro (`67`) | Off / Auto / Cool / Heat / Dry / Fan only; 16–30 °C; Auto / Low / Medium / High fan; vertical swing; Eco / Comfort |
| BAXI Anori JSG35 | `7404` | Magic Cube (`30`) | Off / Cool / Heat; 19–23 °C; Low / Medium / High fan; **Off / Vertical / Horizontal / Both swing**; Turbo / Silence / iFeel / Display |
| Vivax / Midea 48-bit | `7579` | Allone Pro (`67`) | Off / Auto / Cool / Heat / Dry / Fan only; 17–30 °C; Auto / Low / Medium / High fan; tested Kaysun-compatible vertical swing toggle |

AC devices are matched by exact HomeMate virtual remote type `5`, subtype `2`, numeric profile ID and a compatible discovered hub. Merely naming a remote “Daikin”, “BAXI” or “Vivax” is not sufficient.

**BAXI horizontal swing:** v1.4.1 exposes all four swing modes through the existing 13-byte Electra/AUX-style encoder. Carlos (@matexdj) previously confirmed horizontal-only louver movement in an experimental fork. Four distinct 212-duration/38 kHz frames are covered by offline tests, but physical testing of horizontal-only **in the v1.4.1 build itself** has not been separately reported. The iFeel preset does not provide a measured temperature sensor, and Display is momentary. See [BAXI_VALIDATION_GUIDE.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/BAXI_VALIDATION_GUIDE.md).

**Daikin:** Contributor hardware testing on the v1.4.0b1 candidate confirmed Heat, Cool, Off, Auto, Dry, Fan only, low/high fan, vertical swing, Eco and Comfort. Not every possible combination has been independently captured. The Daikin encoder retains its validated OFF signal and existing waveform logic.

**Vivax:** The maintainer physically confirmed Midea 48-bit mode/temperature/fan commands and the alternative Kaysun/Midea swing packet `0xA202FFFFFF7E`; the standard `0xA201FFFFFF7C` did not actuate this unit. Swing is a **relative toggle**; state may diverge after controlling the AC outside Home Assistant. The Kaysun packet is restricted to this profile and must not be used for arbitrary Midea devices.

### Climate state and availability

IR command acknowledgement means ORVIBO accepted the cloud request, **not** that the AC reached a physical mode or temperature. Climate state is the last acknowledged request and starts `unknown` after restart/reload. Setup, polling and reconnect do not automatically emit infrared signals.

Climate availability requires a successful cloud refresh and a compatible cloud-reported online hub route. The cloud may **temporarily cache a hub as online after disconnection**. During a live Allone Pro unplug/replug test on 14 November 2026, its cloud `online` flag eventually became `false`, Vivax became `unavailable`, and both recovered without restart after reconnection. `binary_sensor.orvibo_cloud_connection` correctly remained **On**, because it measures the cloud API, not an individual hub. The exact cloud-side detection delay has not been established; there is no intrusive heartbeat probe or automatic IR test. See [VALIDATION.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/VALIDATION.md).

## Blaupunkt LS 175 soundbar (new in v1.4.1)

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

ORVIBO Cloud is listed in the [HACS default catalog](https://github.com/hacs/default/pull/12441). Install/update **ORVIBO Cloud** in HACS, restart Home Assistant and confirm integration version `1.4.1`. HACS retrieves the release from GitHub once the tag is published. For manual discovery, use `https://github.com/Kosztyk/orvibo_cloud` as a custom HACS Integration repository.

### Manual installation

Back up `/config/custom_components/orvibo_cloud` and unzip the installation archive into `/config`, so `custom_components/orvibo_cloud/manifest.json` exists. **Replace the entire integration directory**, rather than overlaying old experimental files. Restart Home Assistant. Configuration entries, previously selected devices and established IDs are not renamed by this upgrade. No reauthentication is normally needed for a valid existing entry.

To enable a virtual AC or speaker, go to **Settings → Devices & services → ORVIBO Cloud → Configure**, select the device and complete all remaining options pages. The cloud/TV settings, device selection, per-device areas and RF-blind remember/restore/expiry settings are preserved. A matching physical hub need not be explicitly selected as a separate entity.

## Cloud login and servers

Choose the server associated with the HomeMate account: `homemate.orvibo.com`, `germany.orvibo.com`, `china.orvibo.com` or `usa.orvibo.com`. Account affinity may differ from physical location. Do not disable certificate or hostname verification when troubleshooting. Secrets and household identifiers should be redacted before sharing diagnostics.

## RF blind assumed-state options

Where supported, the per-blind device settings include **Remember assumed state**, **Restore after restart** and an optional expiry in whole minutes (`0` disables expiry). A successful Open/Close stores the assumed end state; Stop resets it to unknown. These are not measured positions. Failed commands never overwrite the remembered state. Existing TV, curtain and other integration controls are retained.

## Diagnostics and troubleshooting

The cloud connection binary sensor reports whether the last authenticated coordinator refresh succeeded. It is **not** a hub ping. Cloud snapshots provide the individual hub/remote `online` flags; their freshness depends on ORVIBO. The discovered-device sensor provides a count and sanitized device-type information. Optional raw event capture is diagnostic and may reconnect periodically; it does not intercept phone-app IR commands.

If an AC is unavailable, check the selected virtual remote, its profile ID, a matching compatible hub, and the hub's cloud-reported `online` flag. If a speaker control is unavailable, confirm that the soundbar's device page has the Blaupunkt model selected and that the hub route is online. Do not enable unsupported models merely because their IR format looks similar.

## Validation, credits and licensing

See [VALIDATION.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/VALIDATION.md) for the precise hardware-test scope, acknowledged gaps, test commands and historical PR CI link. The documented HA 2026.11.1 tests do not prove every model/firmware combination; untested physical controls remain qualified.

Maintained by [@Kosztyk](https://github.com/Kosztyk), based on [maycode0-0/orvibo-cloud](https://github.com/maycode0-0/orvibo-cloud). Daikin and BAXI work builds on Carlos [@matexdj](https://github.com/matexdj)'s [PR #5](https://github.com/Kosztyk/orvibo_cloud/pull/5). The RF blind remembered-state feature follows an idea from @craiglemon ([PR #2](https://github.com/Kosztyk/orvibo_cloud/pull/2)).

The repository retains its MIT-licensed original components, while the Daikin encoder is **specifically marked LGPL-2.1-only** with upstream copyright attribution because matching IRremoteESP8266 reset-state constants make independent authorship uncertain. The full LGPL text is distributed in `LICENSES/LGPL-2.1.txt` and inside the integration ZIP. See [THIRD_PARTY_NOTICES.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/THIRD_PARTY_NOTICES.md) and [PROVENANCE_AUDIT.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/PROVENANCE_AUDIT.md). This is a conservative file-specific license disposition, not a legal opinion certifying complete clean-room provenance.
