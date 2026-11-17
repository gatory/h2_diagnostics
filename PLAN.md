# H2 Diagnostics — Plan

Started 2026-11-16. Target: **2026-12-31**.

## Goal

An app on the workstation PC that shows, wirelessly and live, what the H2 EDU is doing:

- a 3D robot that moves with the real one, colored by motor temperature
- both Dex5 hands
- battery, mode and sensor health
- smart warnings
- recording and experiments

## Ground rules

1. **Read-only until the Movement phase.** Nothing publishes to robot DDS topics before then.
2. **Replay first.** Anything that works on live data must also work on a recorded file, so all development can happen without the robot.
3. **One data pipeline.** The live screen, warnings, preflight and recording all use the same snapshot stream.

## Architecture

```
 ROBOT (Jetson Thor)                                  WORKSTATION PC
 ┌─────────────────────────────────────┐   Wi-Fi    ┌──────────────────────────┐
 │ robot DDS (wired, 192.168.123.x)    │            │ Dashboard app            │
 │   └─► h2diag bridge  (read-only)    │ WebSocket  │  3D body · hands · status│
 │        decode → snapshot (~30 Hz)   │ ─────────► │  warnings · preflight    │
 │        health engine → warnings     │            │  record / experiment UI  │
 │        recorder → session files     │ ◄───────── │  (start/stop, markers)   │
 └─────────────────────────────────────┘  app cmds  └──────────────────────────┘
```

- **Why the bridge runs on the Thor:** DDS works over the robot's wired network but not over Wi-Fi. It needs multicast discovery and sends about 1 kHz topics, which Wi-Fi handles poorly. The Thor already sits on that network, so it reads DDS there and sends only compact snapshots over Wi-Fi.
- **Why record on the robot:** a Wi-Fi dropout then never leaves gaps in the data. The app lists and downloads sessions afterwards.
- **"App commands" only control the bridge** (start/stop recording, add markers). They never reach the robot.
- **Fallback:** the same bridge can run on the workstation over the Ethernet cable. Only the address the app connects to changes.

**Tech choices**
- Bridge: a Python package (`h2diag`) using `unitree_sdk2py`.
- App: TypeScript + Vite + three.js (3D) + urdf-loader, opened in its own window (Chrome `--app` at first; package it as a desktop app later if wanted). It runs on Windows or Linux.

## Phases

### 1. Read — Nov 16 – 22
- [ ] `docs/field_map.md`: the meaning and units of every field used. Includes:
  - the 35 body motor slots vs. 31 joints, and the 20 hand motor slots
  - the 2 temperatures per motor
  - the `motorstate`, `bmsstate` and hand `error` bits
  - the battery current and IMU temperature units
- [ ] Controlled tests to pin these down: move single joints by hand, warm up motors, compare left and right.
- [ ] **Wireless check:** on the Thor, confirm it sees `rt/lf/lowstate` on its wired interface **and** can reach the workstation over Wi-Fi.
- [ ] Find an H2 URDF/mesh model (Unitree repos), plus a Dex5 one if it exists.

**Done when:** every field the dashboard will show has a known meaning, and Thor ↔ workstation over Wi-Fi is confirmed.

### 2. Collect — Nov 23 – Dec 6
- [ ] Snapshot format: named joints, SI units, receive timestamps, per-topic rate and age.
- [ ] Sources: live DDS (on the Thor) and replay (from a recorded file).
- [ ] Recorder: session files on disk. Format: Parquet or JSONL, decide in week 2.
- [ ] Health engine, rule layer:
  - a topic stopped or slowed
  - bad checksum
  - motor or hand error bits set
  - temperature limits
  - battery cell spread
  - the two IMUs disagree
  - a joint frozen or reporting invalid numbers
- [ ] `h2diag preflight`: about 10 s of data producing a pass/warn/fail report in the terminal.
- [ ] Fake scenarios for tests: `healthy`, `frozen_joint`, `nan_joint`, `bad_crc`, `stalled_stream`, `motor_code`.
- [ ] WebSocket server streaming snapshots and warnings.

**Done when:** preflight runs on the live robot, and the same code passes the fake scenarios on WSL.

### 3. Dashboard — Dec 7 – 20
- [ ] Main screen: 3D body posed from joint angles and IMU, colored by temperature. If no URDF exists, use a simplified capsule figure.
- [ ] Hand panels in the lower corners: per-motor temperature and position, plus a pressure heat map from 16 pads × 12 cells.
- [ ] Status strip: battery (charge, voltage, current, cell spread), mode, topic health, main board temperatures and fans.
- [ ] Warnings panel and preflight view.
- [ ] Record button. Experiments: name, notes, tags, markers, plus a preflight snapshot at the start.
- [ ] Session browser with replay through the same screen.

**Done when:** you can run an experiment over Wi-Fi and replay it afterwards.

### 4. Test suite — Dec 21 – 31
- [ ] "Out of the ordinary" layer: baselines learned from your own recordings (left/right asymmetry, torque vs. usual at a similar pose, temperature rise rate).
- [ ] Scripted manual protocols, e.g. "move each joint through its range by hand", with pass/fail saved per session.
- [ ] Polish and buffer time for the holidays.

### 5. Movement — January (after this plan)
Commanded test motions, on the gantry only, behind a safety gate with the e-stop. This is the first phase that sends anything to the robot, and it gets its own plan.

## Risks

| Risk | Plan B |
|---|---|
| No H2 URDF available | Capsule figure from joint offsets |
| The Thor can't reach the workstation over Wi-Fi | Run the bridge on the workstation over Ethernet (same app) |
| Python can't keep up with the 1 kHz topics on the Thor | **Measured 2026-11-16 (`rate_probe.py`):** the bridge set (`rt/lf/*` + hands, 281 msg/s) runs at full rate on the Thor. `rt/lowstate` alone holds 1052 Hz. All high-rate topics together (3300 msg/s) keep their rates, but gaps of up to 22 ms appear. So Python handles only the bridge set. If 1 kHz checks (tracking error from `rt/lowcmd`, stall detection) are needed, use a small C++ sidecar (unitree_sdk2). |
| Field meanings stay unknown | Show the raw value with a "?" and leave it out of warnings |
