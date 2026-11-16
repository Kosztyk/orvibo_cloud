# ORVIBO Cloud v1.4.2 validation

## Software checks

The unit suite covers BAXI encoder output, exact profile matching, assumed state, registration and options, binary TLS identity checks, REST redirect rejection, diagnostics redaction, acknowledgement matching, malformed snapshots, door state ordering, reconnects, the LS 175 power lock and TV command scheduling. The packaging check validates HACS layout, brand assets, translations and README synchronization.

```bash
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python tools/check_repository.py
python -m unittest discover -s tests -v
python -m compileall -q custom_components
```

The GitHub validation workflow runs the Python checks, HACS and Hassfest. PR #5's historical run validated the contributor commit. [PR #5 CI run](https://github.com/Kosztyk/orvibo_cloud/actions/runs/43322696393)

## Hardware evidence

| Device and route | Observed result | Validation scope |
| --- | --- | --- |
| Vivax/Midea `7579`, AllOne Pro | The maintainer exercised mode, temperature, fan and Kaysun-compatible `0xA202FFFFFF7E` swing. | The swing command is a relative toggle for this profile. On `1.4.2b5`, the cloud acknowledged Heat and Off after a temporary IR reply outage. |
| Daikin `10502`, AllOne Pro | @matexdj verified Heat 23 °C, Off, Cool 19 °C, low/high fans, vertical swing, Auto, Dry, Fan only, Eco and Comfort. | Physical observations are from `1.4.0b1`. |
| BAXI `7404`, Magic Cube | @matexdj verified Heat/Off/Cool, 19–23 °C, three fan speeds, vertical/both-axis swing, Turbo, Silence, iFeel and Display on `1.4.0b1`. Horizontal-only swing moved only the horizontal louvers on `1.4.1b9`. | The original remote displays 16–32 °C. The integration's expanded range is verified by offline waveform tests. Physical response outside 19–23 °C is pending. |
| Blaupunkt LS 175, AllOne Pro | The maintainer verified Volume +/−, Source, Power toggle, Equalizer and Mute / BT Pair. Power acknowledgements resumed after a temporary IR reply outage on `1.4.2b5`. | The Power switch estimates state from successful cloud acknowledgements. Physical power feedback is unavailable. |
| RF blinds | The maintainer observed Close, **Stopped** and Open in Activity on `1.4.2b5`. | The native cover position state can be Unknown after Stop. |
| Virtual TV remote | The maintainer exercised TV remote controls before this release. | TV sequence limits and IR lock behavior have software coverage. |

The maintainer ran `1.4.2b5` on Home Assistant Core 2026.11.1 with automatic binary TLS verification and seven online cloud devices. A series of soundbar and AC requests received zero decoded replies while cloud polling was healthy. The IR path recovered and subsequent control requests were acknowledged. The initial cause of the reply loss remains unknown. [Contributor test reports](https://github.com/Kosztyk/orvibo_cloud/pull/5)

## Hub availability observations

The ORVIBO Cloud Connection sensor tracks authenticated cloud refreshes. Individual HomeMate device and hub online flags determine route availability.

- On November 14, 2026, the maintainer unplugged the AllOne Pro. Its cloud online flag stayed true initially and later became false, making Vivax unavailable. Both recovered after reconnecting the hub without restarting Home Assistant.
- On November 15, 2026, @matexdj repeated the AllOne Pro outage on `1.4.1b9` with the Magic Cube still connected. The Daikin and its hub reported online after roughly two and five minutes. HomeMate showed them offline around minutes six to seven, with a corresponding `cmd=53` observation. Home Assistant marked Daikin unavailable around minute 7½ while BAXI stayed available. The hub and Daikin recovered after reconnection.

These times describe those test runs. Availability follows the vendor's online status. Setup, polling and reconnection perform discovery without sending device-control commands. [Detailed contributor report](https://github.com/Kosztyk/orvibo_cloud/pull/5)
