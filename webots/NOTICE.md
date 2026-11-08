# Third-party notices

The MIT license in `LICENSE` covers the code and inputs written for this package and the bundled conditional-sharing core. Third-party components keep their own licenses. None of them is redistributed in this package except where stated.

| Component | Use | License | How it is obtained |
|---|---|---|---|
| Webots R2025a (Cyberbotics Ltd.) | Simulator and controller runtime | Apache-2.0 | Base image `cyberbotics/webots:R2025a-ubuntu22.04`, pinned by digest in `sim/Dockerfile` |
| Eclipse Mosquitto 2 | MQTT broker | EPL-2.0 OR EDL-1.0 (BSD-3-Clause) | Image `eclipse-mosquitto:2` |
| Eclipse Paho Python client 1.6.1 | MQTT client | EPL-2.0 OR EDL-1.0 (BSD-3-Clause) | PyPI |
| PyYAML 6.0.2 | YAML loader | MIT | PyPI |
| Ubuntu packages in the base image | Runtime libraries | Various, see the image | Base image |

The world file `sim/worlds/wcs.wbt` uses no Webots PROTO or texture assets. The Webots controller API is used at run time from the image.
