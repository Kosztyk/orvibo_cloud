# IR code provenance review — ORVIBO Cloud v1.4.1

**Scope:** This is a source-level comparison and conservative license treatment,
not a legal opinion or a claim of clean-room authorship. No IR waveform behavior
was changed in the Daikin encoder for v1.4.1.

| Area | Evidence | Finding / disposition |
| --- | --- | --- |
| Daikin reset frame | Python `daikin_arc433.py` 35-byte `reference_bytes` vs. upstream `IRDaikinESP::stateReset()` | The same initial-state byte offsets and values; adaptation cannot be ruled out. File marked LGPL-2.1-only and attributed. |
| Daikin fields and checksum | Python mode/fan/swing/eco/comfort bitfields and 8+8+19-section checksums vs. IRremoteESP8266 `IRDaikinESP` | Protocol-level correspondence; don't assert clean-room origin. LGPL notice and license included. |
| Daikin physical capture | Upstream PR #5 / contributor reports a 584-duration OFF match | Good protocol verification; does not prove software authorship. |
| BAXI Electra/AUX | Python 13-byte candidate encoder vs. `src/ir_Electra.cpp` / `ir_Electra.h` and contributor's HomeMate scenes | Protocol reference and contributor credited; no full provenance proof for every algorithmic detail. |
| Vivax Midea | Python Midea 48-bit encoder vs. `src/ir_Midea.cpp` / `.h` | Protocol reference and confirmed Kaysun swing for one model; not proof of license independence for every field. |
| Original transport | `binary.py`, `control.py`, bundled TLS assets | Byte-for-byte retained from v1.4.0; no new external-code imports. |

References:
- https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Daikin.cpp
- https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Electra.cpp
- https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Midea.cpp
- https://github.com/crankyoldgit/IRremoteESP8266/blob/master/LICENSE.txt
- https://github.com/Kosztyk/orvibo_cloud/pull/5

**Limit:** Without Carlos's complete pre-PR v0.6 patch history and independent
authorship records, there is no basis for a categorical 'independent rewrite'
claim. This release takes the conservative route rather than removing attribution.
