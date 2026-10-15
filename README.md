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

## Diagnostics

Redacted raw event capture can be enabled in the integration options while
troubleshooting. Disable it when finished. It records unsolicited cloud
events; it does not intercept commands sent by the phone app.

## Credits and license

Maintained by **Kosztyk**. Based on the original `maycode0-0/orvibo-cloud`
integration. The original MIT license notice is retained in
`orvibo_cloud/LICENSE`.
