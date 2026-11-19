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
| Read | Nov 16–22 | mostly done; T1 mostly done, T2 done (2026-11-17); T3–T7 pending |
| Collect | Nov 23 – Dec 6 | bridge built early; works live |
| Dashboard | Dec 7–20 | prototype 2026-11-18: 3D + temps, Dex5 hands, ground/gantry frame, strip, warnings, 2D hands, recorder; live twin works per user, full dashboard not yet seen live |
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
robot DDS (wired 192.168.123.x)                      Dashboard (browser app:
  └─► h2diag bridge (read-only, Python)  Wi-Fi WS     React + TypeScript + Vite,
       LiveSource/ReplaySource → H2Diagnostics.tick()  ───►  three.js + urdf-loader)
       → snapshot + health warnings + Recorder  ◄───  recorder commands only
```

- **The bridge runs on the Thor** because DDS (multicast discovery, 1 kHz topics) works poorly over Wi-Fi. Only snapshots cross Wi-Fi: about 10 KB each at 25 Hz.
- **Sessions are recorded on the robot side** so Wi-Fi dropouts don't leave gaps.
- **Fallback:** run the bridge on the workstation over the Ethernet cable.

**Repo layout (reorganized 2026-11-17):** `bridge/` runs on the Thor; `dashboard/` (React prototype, see `dashboard/README.md`) runs on any computer and talks only to the bridge's WebSocket. `examples/` is being retired: `bridge/MIGRATION.md` is the checklist, delete it once the Thor checks pass.

**Bridge layout** (`bridge/h2_diagnostics/`, renamed from `h2diag/` 2026-11-17; the CLI command is still `h2diag`): layers built bottom-up, one job per module. Dependencies point one way, `layout ← sources ← processing ← output, views ← __main__`, and `tests/test_layers.py` enforces it. Classes for things that hold state over time; plain functions/constants otherwise.

| Where | File | Job |
|---|---|---|
| ⓪ root | `layout.py` | Robot facts: joint names + limits, `PR_LINKAGE_JOINTS`, topics, expected rates. Imports nothing (tested). |
| ⑤ root | `__main__.py` | CLI only: parse args, wire layers |
| ① `sources/` (in) | `base.py` | `Source` ABC: `live`, `done`, `topics`, `stats`, `start()`, `now()`, `poll(dt)`, `close()` |
| | `live.py` / `replay.py` | `LiveSource` (DDS) / `ReplaySource` (`.jsonl`, `.gz`), both subclass `Source` |
| | `stats.py` | `TopicStats`: arrival counts, rate, age |
| | `sessions.py` | List/inspect recordings (header + tail only) |
| | `dds.py` | **The DDS gateway:** the only module that imports the SDK (tested). `init`, `subscribe` → `Subscription` (read-only), `hg_type`, type registry, `discover_publications` |
| | `convert.py` | `to_dict`, `num` (JSON-safe values) |
| | `probe.py` | Topic discovery + rate probe (from the examples) |
| ② `processing/` | `state.py` | `RobotState` → snapshot |
| | `health.py` | `HealthMonitor` (holds hysteresis memory) wrapping stateless `evaluate()`. `LIMITS` are **provisional guesses.** |
| | `preflight.py` | Pass/warn/fail verdict (dict) |
| | `pipeline.py` | `H2Diagnostics.tick()` at 50 Hz: source → state → health (+ recorder) |
| | `support.py` | `SupportEstimator`: ground/gantry from knee torque (hysteresis; provisional, `support_raw`) |
| ③ `output/` (out) | `server.py` | WebSocket on :8765 |
| | `recorder.py` | Writes sessions (`.jsonl` + markers) |
| ④ `views/` | `sensors.py` | `live` / `replay` full-screen view (rich) |
| | `report.py`, `tables.py` | Preflight text; sessions/topics/rates/summary tables |

Test data (`bridge/tests/data/`): the 2026-11-12 robot recording (2.2 s at rest) and the 2026-11-13 topic discovery (120 topics).

The SDK decodes every message's bytes into an object on its DDS thread (unavoidable, so 1 kHz topics cost CPU even when dropped); our callback only counts it and keeps the newest per topic (or, while recording, queues every message with its arrival time: `Source.keep_all`, capped at `LiveSource.max_queue`). `to_dict` runs on the main tick for what was kept.

## Commands

```bash
# Thor
python -m h2_diagnostics preflight --live --iface eth10
python -m h2_diagnostics record    --live --name t1_joints    # type note + Enter = marker; Ctrl-C stops
python -m h2_diagnostics serve     --live --iface eth10       # ws://172.16.68.113:8765
python -m h2_diagnostics live      --iface eth10              # full-screen sensor view, red LIVE banner; Δ° column for T1/T2 (Enter resets)
python -m h2_diagnostics live      --iface eth10 --record t1  # view + record; note + Enter = marker
python -m h2_diagnostics live      --iface eth10 --record t6_modes --extra rt/odommodestate  # + research topics (also on `record`)
python -m h2_diagnostics topics    --iface eth10              # discover all topics -> results/discovery/
python -m h2_diagnostics rates     --iface eth10 --set bridge # rates + gaps (bridge | lowstate | all_fast)
# Anywhere
python -m h2_diagnostics replay                              # list recordings (results/sessions + bridge/tests/data), newest first
python -m h2_diagnostics replay 1                            # same view, blue REPLAY banner with recording date/time; .jsonl.gz ok
python -m h2_diagnostics preflight --replay bridge/tests/data/sensors_20261112_150110.jsonl
cd bridge && python -m pytest                          # 68 tests
cd dashboard && npm run dev                            # :5173; ?bridge=ws://172.16.68.113:8765 for the Thor (default ws://localhost:8765)
cd dashboard && npm test && npm run typecheck          # vitest (38) + tsc incl. the snapshot contract
# Workstation setup: uv venv .venv && source .venv/bin/activate && uv pip install -e "bridge[test]"
```

Recordings go to `results/sessions/` (gitignored). They're about 0.5 MB/s, so gzip them before copying with scp.

## Key findings so far

- **Rates on the Thor** (`rate_probe.py`, now `h2diag rates`):
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
  - This matches the SDK2 C++ `H2JointIndex` the user confirmed, and it's what `bridge/h2_diagnostics/layout.py` uses.
  - Unitree's Python `ankle_swing` example, and `examples/.../common.py` which copied it, have **waist and wrists scrambled**. Unitree's H2 joint table (with joint limits, now in `layout.JOINT_LIMITS`) agrees with `layout.py`.
  - **T1 (2026-11-17) confirmed** 12/13/14 waist yaw/roll/pitch and 19/21, 26/28 wrist slots (details in `docs/field_map.md`).
    - The waist was too stiff to move by hand, so it was checked from the relative rotation between the two IMUs: the **main IMU is in the pelvis, `secondary_imu` in the torso**.
    - Slot 21/28 (Unitree name "wrist_yaw") is the hand bending toward the palm / back of the hand. We keep Unitree's names.
    - Slots 20/27 haven't been seen moving yet, so `JOINT_ORDER_VERIFIED` stays `False` until they have.
    - Waist yaw reached ±2.4 rad by hand, past the table's ±1.75 (probably a software limit).
- **`LowState_` has 35 motor slots;** 31–34 are unused (zero).
- **`mode_pr` describes the parallel-linkage joints** (ankles 4/5 and 10/11, waist 13/14: two motors via rods):
  - 0 = PR: slots hold pitch/roll joint angles. This is the default, and both recordings used it.
  - 1 = AB: slots hold raw motor A/B positions, which are not angles. The 3D view must not use them.
  - The bridge doesn't flag this yet (todo).
- **Two motor families:** leg motors 0–3 and 6–9 have `mode` 10 and `vol` always 0, which is normal. The others have `mode` 1 and `vol` ≈ pack voltage.
- **Battery:** 18 cells in mV that sum to `bmsvoltage[0]` (mV). `current` is probably mA, negative = discharge (unconfirmed).
- **Hands (Dex5):**
  - 20 motor slots, four per finger (T2, 2026-11-17): index 0–3, middle 4–7, ring 8–11, pinky 12–15, **thumb 16–19**
  - The thumb reports `q` only (no temperature or status), so `layout.HAND_ACTIVE_MOTORS = 16` currently leaves it out of the display and checks. Todo.
  - 16 pressure pads, 6 of 12 values used, raw values noisy around 0, so calibration is needed
  - Hand motors run warm: 42–66 °C at rest
- **Temperatures:** the waist (especially waist_yaw) is consistently the hottest body joint (48–53 °C). Body IMU temperature is a constant 79 (meaning unknown).
- **FSM state (2026-11-18):** the H2 loco client (`unitree_sdk2/.../h2/loco/h2_loco_client.hpp:242-252`) numbers the states 0 zero_torque, 1 damp, 2 squat, 3 sit, 4 stand_up, **601 start** (G1: 500), now `layout.FSM_STATES`. Reading it via `GetFsmId` (API 7001) would publish a request, so the user chose **read-only: T6 decides the source** (`mode_machine` vs `rt/odommodestate` `mode`, a `unitree_go` type at ~500 Hz). Until then `snap["mode"]["fsm_id_raw"]` is `None` (set it in `processing/state.py:_mode`).
- **Not decodable:** `rt/sportmodestate` / `rt/lf/sportmodestate` (`unitree_hg::SportModeState_`) have no message definition in the SDK. They probably carry the robot's mode/gait; we'd need to write the definition by hand.
- **URDF (2026-11-18), `dashboard/public/renders/`:**
  - `h2_description/H2.urdf` (body, STL meshes): 31 revolute joints; names = layout's with `L_`→`left_`, `R_`→`right_`, `+_joint`; limits match (wrist_yaw rounded to ±1.22). File order differs from slot order (head before arms), so **map by name, never by URDF order**. Fixed links `imu_in_pelvis` / `imu_in_torso` confirm T1. Hands end in a placeholder `left_hand_link` / `right_hand_link`. `tests/test_layout.py` checks names, limits and IMU links against `layout.JOINTS`.
  - `dex5_hands/Dex5-URDF-L|R`: 5 fingers × 4 joints. Finger 1 (`Yaw_11`, `Roll_12`, …) looks like the thumb (= slots 16–19); fingers 2–5 probably index→pinky (= slots 0–15). Inferred 2026-11-18 (unconfirmed on the robot): 2 = index … 5 = pinky by geometry; hand `q` is rad in URDF chain order (T2 ranges match the limits). Mounted at `*_hand_link` with a hand-fitted transform (`DEX5_MOUNT` in `RobotScene.ts`). The left URDF misnames joint `Roll_41L` as `Link_41L`.
  - `H2_Plus` (Sharpa hands) is a different variant; removed.

## Status (end of 2026-11-18) and next steps

**Branch `feat/dashboard`; today's dashboard + bridge work is uncommitted (the user commits).** Checks at end of day: bridge `pytest` 62 passed; dashboard vitest 38, typecheck, lint, build all pass. Everything below was tested on replays (some doctored) in headless Chrome, **not on the Thor**, except where it says "user reported".

- **Bridge:** refactor merged (PR #2). `serve --live` runs on the Thor (the user reported the 3D twin following the robot; no Thor output pasted). The full Thor check (`pytest`, `rates --set bridge`, `topics`, `preflight --live`) hasn't been reported yet.
  - New today: `expected_hz` in `topics`; `support_raw` (`processing/support.py`, below).
- **Dashboard built 2026-11-18** (details: `dashboard/README.md`):
  - scaffold, snapshot contract (`dashboard/src/contract/` ↔ `bridge/tests/test_contract.py`), `BridgeClient` + `useBridge`
  - 3D H2 from the URDF: joints by name, pelvis roll/pitch from the IMU, `mode_pr` freeze, links coloured by motor temperature (amber/red only from bridge warnings), click a link → joint panel
  - **Dex5 hands in 3D:** mounted on `*_hand_link` (fitted by eye against the H2 placeholder hand), fingers posed from hand `q`, coloured per finger motor. Slot → joint is inferred from T2 ranges vs the URDF limits (`field_map.md`). A **view panel** toggles Dex5 / H2-URDF hands (both = overlay).
  - **Ground vs gantry:** the bridge sends `support_raw` (summed |knee tau|, ground above 10 N·m, gantry below 5, PROVISIONAL). The 3D view pins the feet to the floor on the ground and the pelvis on the gantry; view panel override auto / ground / gantry. The IMU can't tell these apart; leg torque can.
  - status strip, warnings panel, 2D hand panels (temps + raw q, pressure tiles, provisional full-scale 500 raw), recorder panel (record / marker / stop; checked end to end on a replay bridge)
- **T1 and T2 recorded** (`results/sessions/20261117_*`); results in `docs/field_map.md`.
- **Recorder bug fixed 2026-11-19 (offline only):** `live --record` kept only the newest message per topic per tick (T1: 66% of `rt/lf/*`, 22% of hands; the `live` loop runs ~22 Hz, not 50). Now `poll()` returns `(topic, data, t)`; while recording the pipeline sets `source.keep_all`, so every message is recorded, stamped with its arrival time. Not yet verified on the Thor (check in `bridge/MIGRATION.md`). Up to one tick right after start is still newest-only.
- **Next:**
  1. User: commit; on the Thor, `git pull`, `serve --live`, open the **full** dashboard (`?bridge=ws://172.16.68.113:8765`) and check: finger poses vs the real hands (right thumb slot 17 reads ~2.9, outside its URDF range, so it's not drawn), the hand mount, a dashboard recording (record, marker, stop, file in `results/sessions/`).
  2. Robot session (gantry + e-stop; markers *before* each action): T9 ground vs gantry (sets the `support.py` thresholds); T6 modes (`--extra rt/odommodestate`) → `_mode()` source; slots 20/27 → `JOINT_ORDER_VERIFIED = True`; right thumb; T5 pressure (10 s untouched first); T4 charging.
  3. Verify the recorder fix on the Thor before T5 (`bridge/MIGRATION.md`).
  4. Dashboard later: session browser (needs a `list_sessions` WS command), the recording's own start time in replay snapshots, smoothing between 20 Hz updates.
  5. **Publisher for the test suite** (user, 2026-11-19): planned, not built. Constraints are in `PLAN.md` §5: a separate module, `dds.py` stays read-only, dry-run first, robot test later.
  6. Smaller: finger names + thumb in `layout.py`; waist_yaw limit; `mode_pr` flag; `rt/lowcmd` decision then delete `examples/`; maybe split `__main__.py` into `cli/`.
- **Open question:** the user asked to "move a finger on the left hand in a fresh test". It's unresolved whether that means moving it by hand while recording (read-only; fine now) or commanding it from software (the first write to the robot, which needs the Movement-phase safety approach and research on the Dex5 command format). Ask before writing any command code.
- **Safety for hand tests:** never force fingers against powered hand motors. Use an unpowered/damped mode or the remote/app gestures.

## Conventions

- Python: `_name` = internal helper; trailing `_` in `LowState_` etc. is Unitree's generated-code naming; `_raw` = unconfirmed field.
- Run the bridge with `python -m h2_diagnostics` (relative imports need package context), or the shorter `h2diag` script (same thing).
- Keep CMake/Python portable across x86_64 and aarch64; no machine-specific paths in code.
- The old `basic.md` brief (FastAPI/TimescaleDB/Next.js/Docker) and the old `PLAN.md` from 2026-11-12 were dropped. Don't revive them.
