# ORVIBO Cloud v1.4.2

Update **ORVIBO Cloud** through HACS and restart Home Assistant. Existing configurations and entity IDs carry over. For a manual installation, copy the complete `custom_components/orvibo_cloud` directory from the tagged source archive into `/config/custom_components`.

## Device support

| HomeMate device | Matching route | Support |
| --- | --- | --- |
| BAXI Anori JSG35 (`7404`) | Magic Cube (`30`) | Heat/Cool at 16–32 °C, four swing modes and existing presets. Physical command tests covered 19–23 °C. The wider range has offline encoder coverage. |
| Daikin ARC433A87-compatible (`10502`) | AllOne Pro (`67`) | Native climate controls, vertical swing, Eco and Comfort |
| Vivax/Midea (`7579`) | AllOne Pro (`67`) | Native climate controls and the verified profile-specific vertical swing toggle |
| Blaupunkt LS 175 | HomeMate speaker type `7`, subtype `0`, on AllOne Pro (`67`) | Opt-in Power, volume, source, equalizer and mute/Bluetooth pairing. Power uses an estimated state. |
| RF blinds and curtains | Type `34` on Magic Cube or AllOne Pro | Open, Close, Stop and optional remembered state. Activity records **Stopped** after an acknowledged Stop. |

The [supported device tables](README.md#supported-ir-climate-profiles) include TV remotes, lights and door status sensors.

## Reliability and security

- Require a matching `cmd=15` acknowledgement before updating assumed control state. A correlated `cmd=42` can provide telemetry for an acknowledged request.
- Reconcile door events with the latest cloud observations and request a fresh device table after reconnect. A malformed snapshot leaves the last successful table in the cache.
- Serialize LS 175 Power commands and limit TV batches to 40 keys including repeats. AC and soundbar commands can run between TV keys.
- Verify the binary TLS certificate chain and hostname using the bundled HomeMate CA. Reject a server presenting the shared client key and honor optional per-host public-key pins.
- Refuse REST redirects, reduce household data in diagnostics, and run the binary push listener when a selected device exposes door events or raw capture is enabled.

The [validation notes](VALIDATION.md) record the live beta observations and software checks for this release.
