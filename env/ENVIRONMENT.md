# Execution environments (as recorded)

Values are copied from the run manifests named in each row. "unknown" means no record in this package states the value. The evidence of record is `records/core/notif-host` (rerun `records/core/notif-docker`) and `records/ros2/final-9ec4e836cb48/a2`, all executed against core snapshot `cs-core-9ec4e836cb48`. Environments of earlier implementation versions follow at the end for lineage.

## Core harness (in-process, no ROS) — current records

| Item | `notif-host` (`records/core/notif-host/manifest.json`) | `notif-docker` (`records/core/notif-docker/manifest.json`) |
|---|---|---|
| Started | 2026-10-30T23:17:04+0900 | 2026-10-30T14:24:18+0000 |
| Python | 3.14.7 (Clang 21.0.0) | 3.12.3 (GCC 13.3.0) |
| Platform | macOS-26.6.2-arm64 | Linux-7.0.14-linuxkit-aarch64, glibc 2.39 (container) |
| PyYAML | 6.0.2 | 6.0.1 |
| Container image for the Docker rerun | — | unknown (the manifest records `container: true` and the Python/PyYAML versions, not the image) |
| Core snapshot | `cs-core-9ec4e836cb48` | same |
| Upstream source | `../rcs-experiments` commit `7bef3ecdd7f59eedba03ed1b819c9770d86d92a7`, tracked blobs copied into `source/conditional-sharing/upstream/` (`upstream/MANIFEST.json`) | same |
| CPU (sweep) | 10 CPUs, shared host, other processes not controlled (`records/core/notif-host/sweep/sweep-summary.json`) | — |

## ROS 2 runs — current records (`records/ros2/final-9ec4e836cb48/a2/*/manifest.json`, `logs/*.jsonl` `env` records)

All 66 run manifests record the same image, package versions, Docker engine and core snapshot; all 282 process `env` records state the same Python, RMW and QoS.

| Item | Value | Evidence |
|---|---|---|
| Runs | 66 (11 scenarios × arms d, a × 3 repetitions), started 2026-10-30 23:24:08 – 23:29:59 (+0900, run ids) | manifest `run_id`, `started`; `summary.md` |
| Core snapshot | `cs-core-9ec4e836cb48` (mounted read-only at `/cs`) | manifest `core_snapshot_id`, `commands` |
| Live code | `live-snapshot-notif.tar.gz` (sha256 `10c87d7a…adc3ca`); manifest `live_sha256` `3519caba…1cce` | manifest `live_sha256`; `snapshots/` |
| ROS 2 distribution | Jazzy | image base `ros:jazzy@sha256:103b6c417973394659af6804d4917cd489b91e5ed22eb7bef263025a3bed2410`; `source /opt/ros/jazzy/setup.bash` in every recorded command |
| Image | `rcs-experiments:jazzy`, id `sha256:c99b70591300f28b63b8ed3f77f753039def35d1b0e13f705ece01166ffa4498` | manifest `image`, `image_id` |
| Dockerfile | `env/Dockerfile` (copy of `docker/Dockerfile` at rcs-experiments `7bef3ecd`) | sets `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`, `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` |
| RMW | `rmw_fastrtps_cpp` 8.4.4-1noble.20260911.054759 | manifest `image_env_probe`; `rmw` in each process `env` record |
| Fast DDS | `ros-jazzy-fastrtps` 2.14.7-1noble.20260911.035410 | manifest `image_env_probe` |
| rclpy | 7.1.12-1noble.20260911.111116 | manifest `image_env_probe` |
| Python / PyYAML in image | 3.12.3 / 6.0.1 | manifest `image_env_probe`; `python` in each process `env` record |
| QoS (every topic in `wire.py`: `/cs/ctl`, `/cs/ready`, `/d/report`, `/d/apply`, `/d/ack`, `/d/inbox/<agent>`, `/cs/a/ltm`, `/cs/a/to/<agent>`) | KEEP_LAST, depth 10000, RELIABLE, TRANSIENT_LOCAL | `source/conditional-sharing/live/cslive/wire.py` `QOS`; `qos` in each process `env` record (282/282) |
| Message type | `std_msgs/String` carrying JSON | `live/cslive/wire.py` docstring |
| Docker engine | 29.9.2 linux/arm64 | manifest `docker` |
| Host OS for Docker | unknown beyond `linux/arm64` server (Docker on the macOS host is implied by the run paths but not recorded as a field) | — |
| Network | one user-defined bridge per run (`cslive-<run_id>`), one container per process, unique `ROS_DOMAIN_ID` per run | manifest `network`, `ros_domain_id`, `commands` |
| Execution order | sequential: repetition 1..3 × 11 scenarios × arm d, a (`live/final.sh`); per run: plan container (no network) → process containers → driver | `live/final.sh`, `matrix.log`, manifest `commands` |
| Step protocol | driver `arm` → `go` → settle by probes of tx/rx counters and core status, two identical probes required; reports and configuration changes belong to different steps and do not overlap | `live/README.md` §1, `live/cslive/proc.py` docstring |
| Fault injection / recovery | not used | `live/README.md` §3 |

The QoS settings are transport configuration of this evaluation, not part of the method: they preserve the order of messages from each writer to each reader, and do not by themselves provide global ordering, exactly-once processing or recovery.

## Not recorded

- CPU model and memory of the Docker VM: unknown.
- Image of the container used for `notif-docker`: unknown.
- Wall-clock settle times are recorded per step in `summary.json` (`settle med/max s`) but are not evaluation results.

## Earlier versions (lineage; not the evidence of record)

The tables below were recorded for `cs-core-c6cef8724cd4` (`records/core/final2-*`, `records/ros2/final-c6cef8724cd4/a1`) and are kept unchanged.

### Core harness (in-process, no ROS)

| Item | `final2-host` (`records/core/final2-host/manifest.json`) | `final2-docker` (`records/core/final2-docker/manifest.json`) |
|---|---|---|
| Started | 2026-10-28T11:51:14+0900 | 2026-10-28T02:51:28+0000 |
| Python | 3.14.7 (Clang 21.0.0) | 3.12.3 (GCC 13.3.0) |
| Platform | macOS-26.6.2-arm64 | Linux-7.0.14-linuxkit-aarch64, glibc 2.39 (container) |
| PyYAML | 6.0.2 | 6.0.1 |
| Container image for the Docker rerun | — | unknown (the manifest records `container: true` and the Python/PyYAML versions, not the image) |
| Upstream source | `../rcs-experiments` commit `7bef3ecdd7f59eedba03ed1b819c9770d86d92a7`, tracked blobs copied into `source/conditional-sharing/upstream/` (`upstream/MANIFEST.json`) | same |
| CPU (sweep) | 10 CPUs, shared host, other processes not controlled (`sweep/sweep-summary.json`) | — |

### ROS 2 runs (`records/ros2/final-c6cef8724cd4/a1/*/manifest.json`, `logs/*.jsonl` `env` records)

| Item | Value | Evidence |
|---|---|---|
| ROS 2 distribution | Jazzy | image base `ros:jazzy@sha256:103b6c41…2410`; `source /opt/ros/jazzy/setup.bash` in every recorded command |
| Image | `rcs-experiments:jazzy`, id `sha256:c99b70591300f28b63b8ed3f77f753039def35d1b0e13f705ece01166ffa4498` | manifest `image`, `image_id` |
| Dockerfile | `env/Dockerfile` (copy of `docker/Dockerfile` at rcs-experiments `7bef3ecd`) | sets `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`, `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` |
| RMW | `rmw_fastrtps_cpp` 8.4.4-1noble.20260911.054759 | manifest `image_env_probe`; `rmw` in each process `env` record |
| Fast DDS | `ros-jazzy-fastrtps` 2.14.7-1noble.20260911.035410 | manifest `image_env_probe` |
| rclpy | 7.1.12-1noble.20260911.111116 | manifest `image_env_probe` |
| Python / PyYAML in image | 3.12.3 / 6.0.1 | manifest `image_env_probe` |
| QoS (every topic in `wire.py`: `/cs/ctl`, `/cs/ready`, `/d/report`, `/d/apply`, `/d/ack`, `/d/inbox/<agent>`, `/cs/a/ltm`, `/cs/a/to/<agent>`) | KEEP_LAST, depth 10000, RELIABLE, TRANSIENT_LOCAL | `source/conditional-sharing/live/cslive/wire.py` `QOS`; `qos` in each process `env` record |
| Message type | `std_msgs/String` carrying JSON | `live/cslive/wire.py` docstring |
| Docker engine | 29.9.2 linux/arm64 | manifest `docker` |
| Host OS for Docker | unknown beyond `linux/arm64` server (Docker on the macOS host is implied by the run paths but not recorded as a field) | — |
| Network | one user-defined bridge per run (`cslive-<run_id>`), one container per process, unique `ROS_DOMAIN_ID` per run | manifest `network`, `ros_domain_id`, `commands` |
| Execution order | sequential: repetition 1..3 × 11 scenarios × arm d, a (`live/final.sh`); per run: plan container (no network) → process containers → driver | `live/final.sh`, `matrix.log`, manifest `commands` |
| Step protocol | driver `arm` → `go` → settle by probes of tx/rx counters and core status, two identical probes required; no fixed quiet window | `live/README.md` §1 (snapshot version) |
| Fault injection / recovery | not used | `live/README.md` §3 |

### Not recorded

- CPU model and memory of the Docker VM: unknown.
- Image digest of the container used for `final2-docker`: unknown.
- Wall-clock settle times are recorded per step in `summary.json` (`settle med/max s`) but are not evaluation results.