# h2diag: the bridge (runs on the Thor)

The bridge is the read-only collector between the H2 and the dashboard app
(`../dashboard/`, any computer). It:
- subscribes to the robot's 20 Hz `rt/lf/*` topics and the Dex5 hand topics
- turns them into one snapshot (named joints, SI units where confirmed)
- runs health checks
- records sessions
- streams everything over WebSocket
- shows it all in the terminal (`live`, `replay`) and probes the DDS network (`topics`, `rates`)

It never publishes to the robot. `tests/test_pipeline.py::test_bridge_never_writes_to_robot` enforces this.

```
robot DDS ──► LiveSource ─┐
                          ├─► Bridge.tick() ─► snapshot + warnings ─► WebSocket :8765 ─► app
.jsonl file ► ReplaySource┘        ├─► Recorder ─► results/sessions/*.jsonl
                                   └─► terminal views (live / replay)
```

## Layout: four layers, dependencies point one way

```
h2diag/
├── __main__.py      CLI only: parses arguments, wires the layers together
├── layout.py        robot facts: joint names + limits, topics, expected rates
├── data/        ①  DATA IN       dds.py · live.py · replay.py · stats.py · sessions.py · probe.py · convert.py
├── processing/  ②  MEANING       state.py (→ snapshot) · health.py (→ warnings) · preflight.py · core.py (Bridge.tick)
├── output/      ③  DATA OUT      server.py (WebSocket) · recorder.py (disk)
└── views/       ④  TERMINAL      sensors.py (live/replay screen) · report.py · tables.py
tests/
├── data/            real robot recording (2026-11-12) + topic discovery (2026-11-13)
└── test_*.py        test_layers.py enforces the arrows below
```

`data ← processing ← output, views`: a layer may import the ones to its left, never
to its right (`tests/test_layers.py` fails otherwise). Each package's `__init__.py`
says what belongs in it.

## Setup

**On the Thor** (in the repo's `.venv`, where `unitree_sdk2py` is already installed):

```bash
cd ~/dev/h2_diagnostics && source .venv/bin/activate
uv pip install -e "bridge[test]"
```

**On the workstation** (replay only, no SDK needed):

```bash
uv venv .venv && source .venv/bin/activate && uv pip install -e "bridge[test]"
```

## Commands

```bash
# Live, on the Thor (all read-only)
python -m h2diag live      --iface eth10               # full-screen sensor view (red LIVE banner)
python -m h2diag live      --iface eth10 --record t1   # ...and record (note + Enter = marker, Enter = reset Δ)
python -m h2diag record    --live --name t1 --seconds 60   # record without the screen
python -m h2diag preflight --live --iface eth10        # 10 s check -> PASS / WARN / FAIL (exit 0/1/2)
python -m h2diag serve     --live --iface eth10        # WebSocket on 0.0.0.0:8765
python -m h2diag snapshot  --live --iface eth10        # print one snapshot as JSON
python -m h2diag topics    --iface eth10               # every DDS topic: type, rate, sample -> results/discovery/
python -m h2diag rates     --iface eth10 --set bridge  # receive rates + gaps (sets: bridge, lowstate, all_fast)

# Recordings, anywhere
python -m h2diag replay                                # list recordings, newest first
python -m h2diag replay 1                              # play #1 (blue REPLAY banner, recording date/time; .gz ok)
REC=bridge/tests/data/sensors_20261112_150110.jsonl
python -m h2diag preflight --replay $REC
python -m h2diag serve     --replay $REC               # loops; --speed 2 for double speed
python -m h2diag topics    --show bridge/tests/data/topics_20261113.json

# Tests
cd bridge && python -m pytest
```

## No data?

- `ip -br addr`: the interface (`eth10` on the Thor) needs a `192.168.123.x` address.
- Is the robot powered on and booted (roughly a minute)?
- Different interface? Pass `--iface <name>`.
- `python -m h2diag topics --iface eth10` lists everything visible on the network.

## WebSocket protocol

- **Server → app:**
  - `{"type": "snapshot", ...}` about 25 times a second (about 10 KB each)
  - `{"type": "ack", "cmd": ..., "ok": ...}` after each command
- **App → server** (recorder only):
  - `{"cmd": "record_start", "name": "...", "notes": "..."}`
  - `{"cmd": "record_stop"}`
  - `{"cmd": "marker", "text": "..."}`

**Snapshot fields:**
- `topics`: rate and age of each topic
- `body`: 31 joints, IMU, modes
- `imu2`
- `battery`
- `mainboard`
- `hands.left`, `hands.right`: 20 motors (16 active), 16 pads × 6 pressure values
- `warnings`
- `recorder`

Fields whose meaning isn't confirmed end in `_raw`; see `docs/field_map.md`.

## Known limits

- **Joint names for slots 12–14 and the wrists are unverified** (`joint_order_verified: false`) until field-map test T1.
- **Health thresholds in `processing/health.py` are provisional guesses.**
- **Recording stores the newest message per topic at each 50 Hz tick**, so the 100 Hz hand data is kept at 50 Hz.
- **Replay rates show the recording's rate**, not the robot's. Rate warnings only run live.
- **No CRC check yet.**
