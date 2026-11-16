# h2diag: the bridge

The bridge is the read-only collector between the H2 and the dashboard app. It:
- subscribes to the robot's 20 Hz `rt/lf/*` topics and the Dex5 hand topics
- turns them into one snapshot (named joints, SI units where confirmed)
- runs health checks
- records sessions
- streams everything over WebSocket

It never publishes to the robot. `tests/test_pipeline.py::test_bridge_never_writes_to_robot` enforces this.

```
robot DDS ──► LiveSource ─┐
                          ├─► Bridge.tick() ─► snapshot + warnings ─► WebSocket :8765 ─► app
.jsonl file ► ReplaySource┘        └─► Recorder ─► results/sessions/*.jsonl
```

## Setup

**On the Thor** (in the repo's `.venv`, where `unitree_sdk2py` is already installed):

```bash
cd ~/dev/h2_diagnostics && source .venv/bin/activate
uv pip install -e "bridge[test]"
```

**On WSL / the workstation** (replay only, no SDK needed):

```bash
python3 -m venv .venv && .venv/bin/pip install -e "bridge[test]"
```

## Commands

```bash
# Live, on the Thor
python -m h2diag preflight --live --iface eth10        # 10 s check -> PASS / WARN / FAIL (exit 0/1/2)
python -m h2diag serve     --live --iface eth10        # WebSocket on 0.0.0.0:8765
python -m h2diag snapshot  --live --iface eth10        # print one snapshot as JSON

# Replay, anywhere
REC=examples/sensor_reading_example/output/sensors_20261112_150110.jsonl
python -m h2diag preflight --replay $REC
python -m h2diag serve     --replay $REC               # loops; --speed 2 for double speed

# Tests
cd bridge && python -m pytest
```

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
- **Health thresholds in `health.py` are provisional guesses.**
- **Recording stores the newest message per topic at each 50 Hz tick**, so the 100 Hz hand data is kept at 50 Hz.
- **Replay rates show the recording's rate**, not the robot's. Rate warnings only run live.
- **No CRC check yet.**
