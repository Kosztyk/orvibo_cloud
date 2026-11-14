# Third-party protocol research, source provenance and licenses (v1.4.1)

ORVIBO Cloud is based on `maycode0-0/orvibo-cloud`; its MIT license is retained
for the original integration and other MIT-covered files. **This does not mean
all files in the repository are MIT-licensed.** File-specific licenses apply.

## Climate contributor

Daikin and BAXI climate support was proposed by **Carlos (@matexdj)** in
[PR #5](https://github.com/Kosztyk/orvibo_cloud/pull/5), with an experimental
Daikin/BAXI fork predating its merge. Subsequent work revised the integration
and added a separately tested Vivax/Midea protocol path. We retain his credit
for the climate code, device protocol research and physical validation.

## Daikin source attribution and license treatment

**Reviewed reference:** [IRremoteESP8266 `src/ir_Daikin.cpp`](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Daikin.cpp),
particularly `IRDaikinESP::stateReset`, `checksum`, power/mode/fan/swing
setters and the multi-section Daikin send layout. The existing Python file
`custom_components/orvibo_cloud/daikin_arc433.py` reproduces the upstream
35-byte initial-state constants and related protocol fields. This is a more
specific match than merely consulting an IR protocol specification.

We **cannot establish independent authorship** of those constants/field
translations from commit chronology alone. We therefore conservatively treat
`daikin_arc433.py` as an LGPL-2.1-covered adaptation, mark it with
`SPDX-License-Identifier: LGPL-2.1-only`, retain the upstream authors' notices,
and include the complete license at
[`LICENSES/LGPL-2.1.txt`](LICENSES/LGPL-2.1.txt). The matching integration
installation includes `custom_components/orvibo_cloud/LICENSES/LGPL-2.1.txt`.

Upstream `ir_Daikin.cpp` lists copyright holders **sillyfrog**,
**crankyoldgit**, and **pasna** (for other Daikin protocol families).
Original upstream library: [IRremoteESP8266](https://github.com/crankyoldgit/IRremoteESP8266),
licensed under [GNU LGPL v2.1](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/LICENSE.txt).
The MIT license at the repository root does **not** supersede the license of
this file or of copyrightable upstream adaptations.

## BAXI/Electra and Vivax/Midea references

The BAXI/Electra 13-byte frame format, field behavior and frame checksum were
studied with reference to
[`src/ir_Electra.cpp`](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Electra.cpp),
which credits **David Conran** and earlier AUX/heatpump research.
The validated BAXI OFF and Heat-on (22°C, low-fan) 212-duration / 38kHz
reference signals originate from HomeMate scenes. The maintainer/contributor
protocol work and upstream references are attributed; a line-by-line source
origin for every field transformation is not independently proved.

The Vivax/Midea 48-bit packet encoder drew on the publicly documented
[`src/ir_Midea.cpp`](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Midea.cpp)
and [`src/ir_Midea.h`](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Midea.h)
protocols and physical testing. The Kaysun `0xA202FFFFFF7E` vertical swing
code is physically verified only for the tested Vivax/Kaysun-compatible model;
on other Midea devices it can perform a different function, including Econo.

## Scope and future provenance work

This review establishes matching Daikin reset constants, upstream copyright,
file-scoped licensing and third-party protocol references. It does **not**
constitute a definitive copyright clearance or confirm an independent clean-room
rewrite of all IR encoders. If further copied portions are identified, retain
upstream notices and apply their applicable license terms. Do not claim
LGPL-covered code was relicensed under MIT. See `PROVENANCE_AUDIT.md` for the
technical comparisons.
