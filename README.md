<img width="512" height="512" alt="logo" src="https://github.com/user-attachments/assets/10a03183-279c-44c6-9bff-c0eaab6959f2" />

# ORVIBO Cloud

A custom Home Assistant integration for ORVIBO Cloud devices, including
curtains controlled through an Allone Pro.

## Experimental IR air conditioning

This local branch is based on ORVIBO Cloud 1.3.2 (upstream commit `3d70f77`).
It adds a `climate` entity for selected HomeMate virtual ACs with a registered
IR profile. The existing domain `orvibo_cloud` is shared with upstream, so use
a separate Home Assistant test instance.

| ORVIBO device / subtype / IR profile | Remote candidate | Hub | Physical verification |
| --- | --- | --- | --- |
| `5 / 2 / 10502` | Daikin ARC433A87-compatible | Allone Pro (type 67) | Works in the shared Home Assistant build, confirmed at Sala Matex |
| `5 / 2 / 7404` | BAXI Anori JSG35 | Magic Cube (type 30) | Works in Home Assistant, with individual controls also tested from a PC |

The Daikin profile exposes the v0.6 controls described below. The BAXI profile exposes OFF, HEAT and COOL,
19–23 C, low/medium/high fan and off/vertical/horizontal/both swing. Fresh requests
start in HEAT at 22 C or COOL at 19 C, with low fan and swing off.
Hardware tests covered heat at 22 C, cooling at 19 and 23 C, all three fan
speeds in COOL, and vertical/both/off swing in COOL. Horizontal-only swing is available but awaits a separate physical check. Other combinations
are generated from the same fields and have not been individually tested.

BAXI exposes Turbo, Silence, iFeel and Display presets confirmed by the user. The preset is exclusive, and Display sends a single
toggle then returns to the normal preset. The iFeel bit can be sent, but
this integration does not emulate temperature readings from the remote.
The user confirmed these four controls on the BAXI on 2026-11-12.
ECO, Sleep, Health, Timer, iClean, Anti-Fungus, ELE.H and iFavor require
additional signal evidence before they can be mapped.
The Daikin profile ports the local v0.6 ARC433A87 encoder for on/off, Auto,
Cool, Dry, Heat and Fan only, 16–30 C, auto/low/medium/high fan and vertical swing or off. The climate preset menu provides ECO, Comfort and
ECO + Comfort. Settings can be changed while off without sending an IR
frame. Turning on restores the last active mode within the current session.
The reference OFF frame still matches the 584 pulse durations and SHA-256
fingerprint recorded by v0.6. On 2026-11-12, the user confirmed that the Daikin responded from the shared Home Assistant build, with both AC profiles configured in the same parallel integration. This confirmation did not enumerate each Daikin setting. The patch credits IRremoteESP8266 as the protocol reference.
The normalized
`irDeviceId` / `irDeviceID` field comes from the local profile diagnostic patch.
The upstream MIT copyright and permission notices are retained in both
license files.

- `protocol.py` extracts the profile ID from the ORVIBO Cloud device table.
- `ac_profiles.py` maps exact device type, subtype and profile IDs to supported
  settings and signal encoders.
- `ac_backend.py` checks the registered hub type, shared hardware UID and
  model, then addresses the virtual AC using the existing TLS client.
- `climate.py` exposes the registered capabilities and reports the last
  acknowledged request as assumed state. On reload the state is unknown.
  Setup and refresh send no IR. A cloud acknowledgement does not report
  whether the air conditioner received or acted on the signal.

To add a model, identify its HomeMate type, subtype, IR profile ID and hub
using sanitized diagnostics. Verify representative signals on that hardware,
then add an encoder and an entry in `IR_PROFILES` with the verified capabilities.
Add offline tests for the exact match, signal fixtures and unsupported settings.
Reload the test integration after adding a new remote in HomeMate.
Brand names alone do not determine compatibility.

### BAXI Anori JSG35 with Magic Cube

HomeMate controls the test unit through a Magic Cube. The virtual remote
reports type `5`, subtype `2` and IR profile `7404`. Home Assistant lists two
Magic controllers with the same model, so model equality alone is insufficient.
The `ac_hub_matches` diagnostics show per-candidate matches for model, cloud
UID and parent relationship without printing their identifiers. A live
read-only lookup returned one online virtual remote for `7404` and two online
type-30 rows with matching model and cloud UID. Neither matched the parent
reference. The physical setup has one Magic Cube for this remote. Treat the
two rows as sharing a cloud route. Both the standalone trial and the
integration address the virtual remote ID plus its cloud UID. From a PC
with Python and `aiohttp` installed, run `python tools/check_baxi_route.py`
for the same read-only lookup. Select the server already used by Home Assistant.
Enter HomeMate credentials in the local hidden prompts. The tool only prints
profile `7404` and hub match flags and writes no credentials or device IDs.

The archived HomeMate [AC layout][historical-ac] and [button handler][historical-button]
identified `311004` as a saved shutdown key. A trial with the TV-style envelope
received a matching `cmd=15` response with `status=1` and the BAXI remained on.
The response did not identify the field that caused rejection.

Static inspection of the installed Android package (5.2.6.308) found that
the Magic Cube AC screen can obtain the signal from the Kookong SDK by
remote profile and AC state, then pass the pulse data and four state values
to ORVIBO's `ir control` path. The app also serializes pulse fields for
scene actions. A manual scene named `BAXI prueba OFF` with one OFF action
can be inspected with `python tools/check_baxi_route.py --scene-off`.
This mode reports only the selected scene's action count and IR metadata.
It does not run the scene. The lookup confirmed a single IR action with
212 pulse durations at 38 kHz. `--scene-test-off` validates those data,
the exact virtual device binding and the matching online Magic Cube,
then offers one direct IR request. This is a separate test of the scene
payload as an IR command. `--save-signal PATH` writes only the pulse data
and four state values after a cloud response and local confirmation that
the unit stopped.

The BAXI stopped on two supervised direct sends using that scene signal.
The registered OFF profile preserves the 212 durations and all four
state fields from the first confirmed send. The fixture contains only
protocol data. Its command path in Home Assistant is covered by simulated
tests. On 2026-11-12, the user confirmed that the BAXI worked from the Home Assistant dashboard using the parallel experimental integration. The user separately confirmed Turbo, Silence, Display and iFeel.

The supervised ON trial reads a separate manual scene, `BAXI prueba ON`,
using `--scene-test-on`. It checks for an ON frame at heat 22 C and low
fan. The BAXI turned on in the supervised test. The registered profile
uses that confirmed frame for both HEAT and the turn-on action. The two
frames preserve their own four state values.

The generated cooling frame at 19 C was also confirmed on the BAXI. The
Electra/AUX field map was checked against the two captured 13-byte frames,
including their checksums. The generator reproduces the verified heating
frame exactly before applying changes to mode, temperature and fan.

Further supervised tests confirmed the visible temperature change from 19 to
23 C, low to high and high to medium airflow, vertical swing, both axes,
and stopping both axes. These commands use the [Electra/AUX field layout](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Electra.h)
with timings and constants measured from the BAXI scene signals.

[historical-ac]: https://github.com/MyStar219/LifeUp_Android/blob/98c215edb56ec0510f46c36c9dd86bb414a0fc9a/HomeMateMobile/src/main/res/layout/activity_conditioner.xml
[historical-button]: https://github.com/MyStar219/LifeUp_Android/blob/98c215edb56ec0510f46c36c9dd86bb414a0fc9a/HomeMateMobile/src/main/java/com/orvibo/homemate/view/custom/IrButton.java

### Installing a reviewed build in a test instance

This branch is local. For a manual test, copy `custom_components/orvibo_cloud`
from this checkout into the test instance's `/config/custom_components/`.
Restart, add **ORVIBO Cloud** from **Settings → Devices & services**, and select
the virtual AC. The hub can be unselected as long as the account discovers it.

Once a reviewed build is available in a GitHub repository you can access,
open **HACS → Custom repositories**, add that repository URL with type
**Integration**, download the reviewed build, and restart the test instance.
Confirm the selected version or branch contains this experiment before
downloading. The upstream repository URL above installs upstream.
The experiment and upstream share the same installation path, so installing
one over the other replaces its files. [HACS integration documentation](https://www.hacs.xyz/docs/use/repositories/type/integration/)

### Privacy and validation

ORVIBO Cloud uses the HomeMate account for discovery and sends commands with
device and household identifiers to the configured ORVIBO server. This
experiment uses the existing TLS validation. Keep raw event capture disabled
during ordinary use. Review diagnostics and remove household, room and device
names and identifiers before sharing. Keep config entries, credentials,
password hashes, tokens, backups and raw captures outside the repository.

Run `python -m unittest discover -s tests -v` and
`python tools/check_repository.py` from the repository root. Tests exercise the
wire payload, profile matching, failure handling and Home Assistant command
path with simulated dependencies. Hardware and a live Home Assistant
installation require separate validation.


## Install with HACS

Before inclusion in the default HACS catalog, add this repository as a custom
integration:

1. Open **HACS** in Home Assistant and select **Custom repositories** from the
   menu.
2. Add `https://github.com/Kosztyk/orvibo_cloud` and select **Integration**.
3. Install **ORVIBO Cloud** and restart Home Assistant.
4. Open **Settings > Devices & services > Add integration**, select **ORVIBO
   Cloud**, sign in and select your devices.

HACS manages subsequent downloads and version upgrades. After acceptance into
the default HACS catalog, the custom-repository step will no longer be needed.

## Manual installation and upgrades

1. Copy the `orvibo_cloud` folder from this archive into
   `/config/custom_components/`, replacing existing integration files.
2. Restart Home Assistant.
3. For a new setup, open **Settings > Devices & services > Add integration**
   and select **ORVIBO Cloud**. Existing installations can keep their integration
   entry, server, and device selections.
4. Sign in with the account used in the ORVIBO Home or HomeMate app, choose
   your home, select the devices to add, and assign their areas.

The integration folder must be `/config/custom_components/orvibo_cloud/`
and contain `manifest.json` directly inside it.

## Cloud server

Use the server that contains your app's devices. The available servers are
`homemate.orvibo.com`, `germany.orvibo.com`, `china.orvibo.com`, and
`usa.orvibo.com`. International accounts can try `homemate.orvibo.com` first.
The server can be changed in the integration's configuration options.

## Verified ORVIBO binary cloud TLS (v1.3.2)

The port-10002 connection validates the ORVIBO self-signed CA against a bundled, fingerprint-checked trust anchor and requires a matching DNS hostname. A legacy Basic Constraints extension necessitates relaxing only the `VERIFY_X509_STRICT` check; `CERT_REQUIRED`, certificate-chain validation and hostname checking remain active. This legacy CA has been corroborated in two public integrations and observed on the live ORVIBO server, but has not been verified independently with the manufacturer. No insecure TLS fallback is provided.

The version also fixes diagnostics account-email redaction, prevents cloud refreshes from overriding manually assigned device areas, synchronizes English translations, and backs off capture reconnections while stopping on rejected logins.

## Allone Pro RF blinds

RF blinds associated with an Allone Pro or compatible hub expose **Open**,
**Close**, and **Stop**. The integration detects their hub relationship from
the discovered device list, even if the hub itself is not selected for addition
to Home Assistant.

RF commands do not provide a measured position. These covers use assumed
state and do not expose a percentage slider. Directly controlled curtain
motors retain their existing position support.

### Optional remembered open/closed state

Open **Settings > Devices & services > ORVIBO Cloud > Configure**. Keep the
desired devices selected, then use each RF blind's **Device settings** step:

- **Remember assumed open/closed state**: disabled by default, independently
  for each blind. A successful Open command assumes open, a successful Close
  command assumes closed, and a successful Stop command returns to unknown.
- **Restore assumed state after restart**: disabled by default. When remembering
  is enabled, restore the last successful command and its original timestamp
  after a Home Assistant restart or integration reload.
- **Assumed state expiry**: whole minutes, with `0` meaning no expiry. An expired
  assumption returns to unknown automatically. Restarting does not extend its
  lifetime. Expired history remains available for diagnostics.

Finish every device step to save the settings. The same options are available
during initial setup. Existing installations keep the unknown RF state until
remembering is explicitly enabled.

| Successful Home Assistant command | Assumed state | Percentage |
| --- | --- | --- |
| Open | Open | Unknown |
| Close | Closed | Unknown |
| Stop | Unknown | Unknown |

Remembered states remain marked `assumed_state: true`. Enabled blinds expose
`last_action`, `last_action_time` (UTC), `state_source: last_successful_command`,
and `assumption_expired`. Failed commands leave the prior history intact, and
ordinary cloud refreshes do not overwrite it with placeholder position values.

This records an accepted command, not confirmation that the motor reached an
endpoint. Movements made in the HomeMate app or with a physical remote are not
detected, so the assumption can become stale. Restoration uses Home Assistant's
standard restore-state storage; an abrupt power loss can lose recent history.

## Diagnostics

Redacted raw event capture can be enabled in the integration options while
troubleshooting. Disable it when finished. It records unsolicited cloud
events; it does not intercept commands sent by the phone app.

## Credits and license

Maintained by **Kosztyk**. Based on the original `maycode0-0/orvibo-cloud`
integration. The original MIT license notice is retained in
`LICENSE`.

The remembered RF state feature builds on the idea proposed by **craiglemon**
in [pull request #2](https://github.com/Kosztyk/orvibo_cloud/pull/2).

## Validation

The CI checks verify packaging, metadata and Python syntax. Version 1.3.2 adds
local TLS handshake tests for legacy-CA compatibility, hostname and trust-chain
rejection, plus rejected-login and bounded reconnect-backoff tests.
The previous 51-check runtime test suite is not included in the public repository,
so those earlier results are historical and not reproduced here. See
[VALIDATION.md](VALIDATION.md) in the repository root for the scope and
limits of the published checks.
