<img width="512" height="512" alt="ORVIBO Cloud" src="https://github.com/user-attachments/assets/10a03183-279c-44c6-9bff-c0eaab6959f2" />

# ORVIBO Cloud for Home Assistant

Native Home Assistant integration for **ORVIBO Cloud / HomeMate** with Allone Pro RF blinds, infrared TV remotes and selected air-conditioner remotes. Supports authenticated ORVIBO cloud connectivity and optional remembered blind state.

**Latest stable release: v1.4.0** · [Release notes](https://github.com/Kosztyk/orvibo_cloud/blob/main/RELEASE_NOTES_1.4.0.md) · [Changelog](https://github.com/Kosztyk/orvibo_cloud/blob/main/CHANGELOG.md) · [Validation](https://github.com/Kosztyk/orvibo_cloud/blob/main/VALIDATION.md)

## Features

- **RF blinds:** Open / Close / Stop with accurate capability reporting, optional persisted **assumed** open/closed state and expiry.
- **TV remotes:** Home Assistant `remote` entity plus command buttons for supported Allone/Allone Pro virtual TV remotes.
- **IR climate:** Native `climate` entities for the exact HomeMate AC profiles listed below. Generates IR locally; **does not require scenes** or the HomeMate app to be running.
- **Cloud diagnostics:** Connectivity, discovered devices, device/hub match metadata and optional raw event capture.
- **Security:** Authenticated cloud TLS with hostname verification and pinned bundled CA, carried over unchanged from v1.3.2.

## Supported IR climate profiles (v1.4.0)

| HomeMate virtual AC | Profile ID | Compatible hub | Supported controls |
| --- | --- | --- | --- |
| Daikin ARC433A87-compatible | `10502` | Allone Pro (`67`) | Off/Auto/Cool/Heat/Dry/Fan only; 16–30 °C; Auto/Low/Medium/High fan; vertical swing and ECO/Comfort presets |
| BAXI Anori JSG35 | `7404` | Magic Cube (`30`) | Off/Cool/Heat; 19–23 °C; Low/Medium/High fan; vertical/both swing and Turbo/Silence/iFeel/Display presets |
| Vivax / Midea 48-bit | `7579` | Allone Pro (`67`) | Off/Auto/Cool/Heat/Dry/Fan only; 17–30 °C; Auto/Low/Medium/High fan; Kaysun-compatible vertical swing toggle |

Climate entities are created only for **selected** virtual remotes with an exact `(device type 5, subtype 2, profile ID)` match and a matching supported IR hub. Merely naming a device “Vivax” or “Midea” does not enable the encoder. Other Midea/Vivax remote profiles are **not automatically supported**.

### Vivax / Midea: native 48-bit IR controls

Profile `7579` uses local Midea 48-bit full-state IR frames with checksum and an inverted companion frame. There is **no scene-based fallback**. The maintainer physically confirmed HVAC modes, temperature and fan controls on their Vivax, and confirmed that the alternative **Kaysun/Midea** Swing command `0xA202FFFFFF7E` moves the louvers. The standard Midea swing toggle `0xA201FFFFFF7C` did not work on that unit.

**Vertical swing is relative**, not a known absolute position. After restart or external control, Home Assistant cannot know the actual louver position. The integration sends a swing toggle when the user changes Off/Vertical while the AC is active; always verify the first change physically. The Kaysun command may operate Econo on other Midea models, which is why it is restricted to this exact profile.

### Daikin and BAXI notes

Daikin supports locally remembered climate settings while off. BAXI only sends settings while active, and its horizontal-only swing option is intentionally not offered until physically verified. BAXI's iFeel feature does **not** add a temperature sensor; its Display action is a momentary command. The contributor reports physical tests on their Daikin and BAXI units; not every possible advanced combination has been independently reverified in this production package.

### Important: state is assumed, not measured

HomeMate/ORVIBO binary control acknowledgements indicate accepted commands; they do not confirm that the air conditioner received the IR light or reached a specific temperature. Climate state starts unknown after reload and records **the last acknowledged request**. Commands sent from the HomeMate mobile app or a physical remote do not update the Home Assistant assumed state. Neither setup nor polling emits IR.

## Installation

### HACS (recommended)

[ORVIBO Cloud is listed in the HACS default catalog](https://github.com/hacs/default/pull/12441). Open HACS, search for **ORVIBO Cloud**, install or update it, then restart Home Assistant. If it is not listed in your HACS installation, add `https://github.com/Kosztyk/orvibo_cloud` as a **Custom repository → Integration**.

Open **Settings → Devices & services → Add integration → ORVIBO Cloud**, sign in, choose your home and select devices. Existing installations keep the `orvibo_cloud` configuration entry and entity unique IDs when upgrading from v1.3.2.

### Manual installation / upgrade

Copy `custom_components/orvibo_cloud/` to `/config/custom_components/orvibo_cloud/` so that `manifest.json` is directly inside the folder. Back up any previous `orvibo_cloud` directory and **replace the entire folder** when upgrading from test betas, to remove obsolete scene/probe modules. Restart Home Assistant.

**Climate remotes:** In **ORVIBO Cloud → Configure**, select the desired virtual IR remote and save. The associated IR hub must be discoverable and compatible; you do not need to select the hub as a separate entity. Reload the integration if you change HomeMate's virtual remotes.

## Cloud server and login

Use the region/server to which your ORVIBO account belongs. The integration exposes `homemate.orvibo.com`, `germany.orvibo.com`, `china.orvibo.com` and `usa.orvibo.com`. The app may use account-specific server lookup; choosing a server solely from physical location is not always reliable. Do not change credentials or turn off TLS verification as a troubleshooting shortcut.

## Allone Pro RF blinds

RF blinds associated with a compatible hub expose Open, Close and Stop without a percentage slider. Position is **not** measured. Curtain motors with direct position support retain their existing capabilities.

The integration's **Device settings** options offer independently per blind:

- **Remember assumed open/closed state:** defaults off. A successful Open sets assumed open, Close sets assumed closed; Stop returns unknown.
- **Restore after restart:** defaults off. When enabled, restores the last accepted command with its original timestamp.
- **Assumed-state expiry:** configurable in whole minutes; `0` disables expiry. Once expired, the assumed open/closed state becomes unknown again.

History attributes include `last_action`, `last_action_time`, `state_source` and `assumption_expired`. External app or wall-remote actions cannot be detected, so the assumption may be stale. A failed command does not overwrite the remembered state.

## Diagnostics and troubleshooting

ORVIBO Cloud exposes a cloud connectivity binary sensor and discovered-device count/family sensors. Integration diagnostics redact account identifiers and credentials and include sanitized remote profile and hub matching information. Before sharing diagnostics, review fields for privacy and redact personally identifying household data.

Optional **raw event capture** listens for unsolicited cloud events; it does not intercept phone-app commands or measure IR. Some ORVIBO servers close these long-running capture connections periodically. Disable raw capture when not diagnosing a protocol issue. The normal polling/control path remains separate.

If a climate entity is missing, confirm the virtual remote is selected, its `irDeviceId` matches the exact profile above, and the compatible hub is online. An unavailable or unmatched hub prevents IR control. No IR is sent simply by adding the entity.

## Compatibility, tests and release process

- Production version: **1.4.0**. Tested by the maintainer on Home Assistant **2026.11.1** for the Vivax/Midea path. Normal HACS, Hassfest, packaging, protocol and security test workflows are included in `.github/workflows/`.
- The v1.4.0 changes use Home Assistant 2026.11 native climate temperature properties and scoped device-registry APIs. Version 2026.11.1 is the documented field-test environment; other versions require separate verification.
- The offline tests cover profile detection, Midea checksums/inverted IR packets, climate command validation, hub associations, registry migration, packaging and existing TLS behavior (with `pycryptodome` installed). They cannot prove physical action.
- Maintainer release process: see [HACS_PUBLISHING.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/HACS_PUBLISHING.md) and [scripts/publish_v1.4.0.sh](https://github.com/Kosztyk/orvibo_cloud/blob/main/scripts/publish_v1.4.0.sh).

## Credits and license

Maintained by [@Kosztyk](https://github.com/Kosztyk). Based on the original [maycode0-0/orvibo-cloud](https://github.com/maycode0-0/orvibo-cloud), with its MIT license retained. Climate support builds on **[@matexdj](https://github.com/matexdj)**'s work, merged in [PR #5](https://github.com/Kosztyk/orvibo_cloud/pull/5), together with maintainer Home Assistant compatibility work and physically tested Vivax/Midea support. The RF remembered-state work follows an idea proposed by **craiglemon** in [PR #2](https://github.com/Kosztyk/orvibo_cloud/pull/2).

See [THIRD_PARTY_NOTICES.md](https://github.com/Kosztyk/orvibo_cloud/blob/main/THIRD_PARTY_NOTICES.md) for IR protocol reference attribution and associated license information.
