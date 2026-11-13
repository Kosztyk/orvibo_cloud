# Third-party protocol research and acknowledgements

ORVIBO Cloud is based on the original `maycode0-0/orvibo-cloud` integration. Its existing MIT license and upstream notices are retained in `LICENSE` and `custom_components/orvibo_cloud/LICENSE`.

## Climate contributor

The Daikin and BAXI climate integration work was proposed by **@matexdj** in [Kosztyk/orvibo_cloud PR #5](https://github.com/Kosztyk/orvibo_cloud/pull/5). This v1.4.0 release incorporates a revised implementation of that proposal, Home Assistant compatibility work and an independently developed Vivax/Midea path. Thank you to the contributor for the hardware testing and protocol work.

## IRremoteESP8266 reference material

The Daikin ARC433-family, Electra/AUX-family and Midea 48-bit IR frame layouts were studied with reference to the [IRremoteESP8266 project](https://github.com/crankyoldgit/IRremoteESP8266), including `ir_Daikin.cpp`, `ir_Electra.h` and `ir_Midea.cpp` / `ir_Midea.h`. The library is published under the [GNU Lesser General Public License v2.1](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/LICENSE.txt); its authors retain their rights.

This repository does not bundle or dynamically link the IRremoteESP8266 compiled library. The Python implementations were written using published protocol descriptions and signal/fixture comparisons. This attribution is not a substitute for a full third-party intellectual-property review if adapted code is later added; do not assume the existing MIT license relicenses third-party LGPL work.

The documented `0xA202FFFFFF7E` code is a vertical swing toggle only for the tested Vivax/Kaysun-compatible profile; on other Midea variants it may represent an Econo command. Do not apply it universally.
