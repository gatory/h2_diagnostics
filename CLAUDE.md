# CLAUDE.md: H2 Diagnostics

A diagnostic dashboard for one **Unitree H2 EDU** humanoid: Dex5-1P tactile hands, NVIDIA Jetson AGX Thor onboard. The details live in:
- `PLAN.md`: the plan and schedule
- `docs/field_map.md`: what each robot field means
- `bridge/README.md`: the bridge's usage

This file is the short version, plus context from planning conversations.

## Goal and scope (agreed 2026-11-16, replacing the earlier messy plans)

An app on the **workstation PC**, connected **wirelessly**, styled like a minimal "Tesla dashboard":
- **Main screen:** a live 3D robot (URDF + three.js) that moves with the real one, with each motor colored by temperature
- **Lower corners:** left and right Dex5 hands (motor temps, finger motion, pressure heat map)
- **Status strip:** battery, robot mode, sensor and topic health
- **Health checks + "smart" warnings** for anything out of the ordinary, and a **preflight** pass/warn/fail report
- **Recording** (raw capture) and **experiments** (recording + name, notes, tags, markers, preflight snapshot; replay and compare later)

Progression: **read → collect → dashboard → test suite → movement.**
- Deadline 2026-12-31 for the first four.
- Movement comes in January and gets its own plan.

| Phase | Dates | State |
|---|---|---|
| Read | Nov 16–22 | mostly done; robot tests T1–T7 pending |
| Collect | Nov 23 – Dec 6 | bridge built early; works live |
| Dashboard | Dec 7–20 | not started |
| Test suite | Dec 21–31 | not started |

## Ground rules

1. **Read-only until the Movement phase.** Nothing publishes to the robot. `bridge/tests/test_pipeline.py::test_bridge_never_writes_to_robot` enforces this in the bridge. Any future command-sending code must be separate, need explicit user approval, and run on the gantry only, with the e-stop in reach.
2. **Replay first.** Everything must also run on a recorded `.jsonl`, so development works without the robot.
3. **One pipeline.** The live view, warnings, preflight and recording all use the same snapshot.
4. **H2-specific, confirmed topics only.** Unitree's shared software stack also publishes topics meant for other models (`rt/dog_*`, `unitree_go` types, Dex3). The bridge uses only `unitree_hg` topics whose contents have been checked.
5. **Unconfirmed fields end in `_raw`.** They're shown with a "?", never used for warnings, and renamed once confirmed.

## Machines and workflow

- **Code is written on the workstation** (since 2026-11-16; previously WSL2): native Ubuntu 22.04, x86_64, Python 3.10, at `/home/pdol/dev/unitree/h2_diagnostics`, uv venv at `.venv`.
  - Wired on the lab network: `enp0s31f6` = `172.16.66.95/21`, the same /21 as the Thor's `172.16.68.113`.
  - It is **not** on the robot's DDS network (192.168.123.x), so local runs are replay/test checks, plus WebSocket clients of a bridge running on the Thor. **Never claim robot behavior was verified unless it came from the Thor's output.**
- **The user commits and pushes,** then runs `git pull` on the **Thor** (aarch64) at `~/dev/h2_diagnostics` and pastes the output back.
- **Thor network:** `eth10` has `192.168.123.163` (the robot's internal DDS network) **and** `172.16.68.113/21` (the lab network, reachable from the workstation; ping confirmed). The Thor has no Wi-Fi interface itself.
- **Thor Python:** a uv venv at `~/dev/h2_diagnostics/.venv` (`source .venv/bin/activate` in each SSH session).
  - `unitree_sdk2_python` is at `~/dev/unitree_sdk2_python`
  - CycloneDDS is at `~/cyclonedds/install`, installed with `CYCLONEDDS_HOME=~/cyclonedds/install uv pip install -e ~/dev/unitree_sdk2_python`
- **Local SDK clones** on the workstation for reference: `~/dev/unitree/{unitree_sdk2,unitree_sdk2_python,unitree_ros2}`.
- **We use `unitree_sdk2_python`, not `unitree_ros2`.** Both read the same DDS topics, and ROS 2 adds setup without adding data. Its H2 message set is identical to the SDK's. The C++ `unitree_sdk2` is reserved for a possible 1 kHz helper.

## Architecture

```
ROBOT (Thor)                                         WORKSTATION
robot DDS (wired 192.168.123.x)                      Dashboard app (planned:
  └─► h2diag bridge (read-only, Python)  Wi-Fi WS     TypeScript + Vite + three.js
       LiveSource/ReplaySource → Bridge.tick()  ───►  + urdf-loader, own window)
       → snapshot + health warnings + Recorder  ◄───  recorder commands only
```

- **The bridge runs on the Thor** because DDS (multicast discovery, 1 kHz topics) works poorly over Wi-Fi. Only snapshots cross Wi-Fi: about 10 KB each at 25 Hz.
- **Sessions are recorded on the robot side** so Wi-Fi dropouts don't leave gaps.
- **Fallback:** run the bridge on the workstation over the Ethernet cable.

**Bridge layout** (`bridge/h2diag/`): one module, one job; sources are swappable adapters.

| File | Job |
|---|---|
| `layout.py` | Robot facts: joint names, topics, counts |
| `sources.py` | `LiveSource` (DDS) / `ReplaySource` (`.jsonl`), same interface |
| `state.py` | `TopicStats` (rates) + `RobotState` → snapshot |
| `health.py` | Snapshot → warnings. `LIMITS` are **provisional guesses.** |
| `recorder.py` | Sessions in the same `.jsonl` format as `stream_sensors.py`, with markers |
| `core.py` | `Bridge.tick()` at 50 Hz |
| `server.py` | WebSocket on :8765 |
| `preflight.py` | Pass/warn/fail report |
| `__main__.py` | CLI |

DDS callbacks only store the newest message and count it; all decoding happens on the main tick, because Python decode throughput is the bottleneck.

## Commands

```bash
# Thor
python -m h2diag preflight --live --iface eth10
python -m h2diag record    --live --name t1_joints    # type note + Enter = marker; Ctrl-C stops
python -m h2diag serve     --live --iface eth10       # ws://172.16.68.113:8765
# Anywhere
python -m h2diag preflight --replay examples/sensor_reading_example/output/sensors_20261112_150110.jsonl
cd bridge && python -m pytest                          # 19 tests
# Workstation setup: uv venv .venv && source .venv/bin/activate && uv pip install -e "bridge[test]"
```

Recordings go to `results/sessions/` (gitignored). They're about 0.5 MB/s, so gzip them before copying with scp.

## Key findings so far

- **Rates on the Thor** (`rate_probe.py`):
  - `rt/lowstate` ~1052 Hz, `rt/lf/*` 20 Hz, hands 100 Hz, `rt/lowcmd` ~1 kHz (only when a controller is active)
  - The bridge's set (~280 msg/s) is clean.
  - All the fast topics together (~3300 msg/s) keep their rates but show gaps up to 22 ms. **Python handles only the light set.** 1 kHz work (e.g. tracking error from `rt/lowcmd`) would need a C++ sidecar.
- **`rt/` is ROS 2's topic prefix** (`rr/` = service reply). **`lf/` is inferred to mean "low frequency"**: the same types at about 1/50th of the rate, unconfirmed. Possible test T8: compare `lf/lowstate` with `lowstate` by `tick` to see whether it's down-sampled or filtered.
- **Joint order (0–30):**
  ```
  L hip pitch/roll/yaw, knee, ankle roll/pitch (0-5)
  R same (6-11)
  waist yaw/roll/pitch (12-14)
  L shoulder pitch/roll/yaw, elbow, wrist roll/pitch/yaw (15-21)
  R same (22-28)
  head pitch/yaw (29-30)
  ```
  - This matches the SDK2 C++ `H2JointIndex` the user confirmed, and it's what `bridge/h2diag/layout.py` uses.
  - Unitree's Python `ankle_swing` example, and `examples/.../common.py` which copied it, have **waist and wrists scrambled**.
  - `JOINT_ORDER_VERIFIED = False` until robot test T1.
- **`LowState_` has 35 motor slots;** 31–34 are unused (zero).
- **`mode_pr` describes the parallel-linkage joints** (ankles 4/5 and 10/11, waist 13/14: two motors via rods):
  - 0 = PR: slots hold pitch/roll joint angles. This is the default, and both recordings used it.
  - 1 = AB: slots hold raw motor A/B positions, which are not angles. The 3D view must not use them.
  - The bridge doesn't flag this yet (todo).
- **Two motor families:** leg motors 0–3 and 6–9 have `mode` 10 and `vol` always 0, which is normal. The others have `mode` 1 and `vol` ≈ pack voltage.
- **Battery:** 18 cells in mV that sum to `bmsvoltage[0]` (mV). `current` is probably mA, negative = discharge (unconfirmed).
- **Hands (Dex5):**
  - 20 motor slots, 16 active; 16–19 report `q` only
  - 16 pressure pads, 6 of 12 values used, raw values noisy around 0, so calibration is needed
  - Hand motors run warm: 42–66 °C at rest
- **Temperatures:** the waist (especially waist_yaw) is consistently the hottest body joint (48–53 °C). Body IMU temperature is a constant 79 (meaning unknown).
- **Not decodable:** `rt/sportmodestate` / `rt/lf/sportmodestate` (`unitree_hg::SportModeState_`) have no message definition in the SDK. They probably carry the robot's mode/gait; we'd need to write the definition by hand.
- **No H2 URDF found locally yet.** Fallback for the 3D view: a capsule figure.

## Status (2026-11-16) and next steps

- **Live preflight on the Thor works:**
  - every topic at its exact expected rate
  - battery 75%, 70.7 V, 6 mV spread
  - waist_yaw 48 °C; hands 54/51 °C
  - The false "half rate" startup warnings were a rate-window bug, fixed in `state.py` with `tests/test_rates.py`. **That fix may still need committing and pushing.**
- **Next:**
  1. Re-run preflight on the Thor (expect PASS).
  2. Robot tests from `docs/field_map.md`, using `h2diag record`:
     - **T1 joint order** and **T2 finger mapping** first (both needed for the 3D model)
     - then T5 pressure, T6 modes, T3 thermal (10 min rest/hold), T4 charging
  3. Make `ReplaySource` read `.gz`.
  4. Fix `common.py` joint labels.
  5. Add the `mode_pr` PR/AB flag to the snapshot.
  6. Find the H2 URDF.
  7. Start the dashboard app.
- **Open question:** the user asked to "move a finger on the left hand in a fresh test". It's unresolved whether that means moving it by hand while recording (read-only; fine now) or commanding it from software (the first write to the robot, which needs the Movement-phase safety approach and research on the Dex5 command format). Ask before writing any command code.
- **Safety for hand tests:** never force fingers against powered hand motors. Use an unpowered/damped mode or the remote/app gestures.

## Conventions

- Python: `_name` = internal helper; trailing `_` in `LowState_` etc. is Unitree's generated-code naming; `_raw` = unconfirmed field.
- Run the bridge with `python -m h2diag` (relative imports need package context), or the `h2diag` script.
- Keep CMake/Python portable across x86_64 and aarch64; no machine-specific paths in code.
- The old `basic.md` brief (FastAPI/TimescaleDB/Next.js/Docker) and the old `PLAN.md` from 2026-11-12 were dropped. Don't revive them.
