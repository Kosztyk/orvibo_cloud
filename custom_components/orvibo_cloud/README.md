<img width="512" height="512" alt="logo" src="https://github.com/user-attachments/assets/10a03183-279c-44c6-9bff-c0eaab6959f2" />

# ORVIBO Cloud

A custom Home Assistant integration for ORVIBO Cloud devices, including
curtains controlled through an Allone Pro.

## Installation and upgrades

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

51 automated checks passed on Home Assistant 2026.10.2, including RF commands,
optional per-blind state, startup restoration, expiry, and configuration flows.
These checks use mocked ORVIBO command replies.
