# Dashboard (prototype started 2026-11-18)

The viewer half of the project. It runs on **any computer** on the same network as
the robot's Thor and only talks to the bridge, never to the robot directly.

```
ROBOT (Thor)                                   ANY COMPUTER
bridge/  (h2diag serve --live)  ── WebSocket ──►  dashboard/  (this folder)
ws://<thor-ip>:8765                ◄── recorder commands only
```

- **Stack:** React 19 + TypeScript + Vite, three.js + urdf-loader for 3D, vitest for tests.
- **Main screen:** live 3D robot colored by motor temperature; Dex5 hands in the lower
  corners; status strip (battery, mode, topic health); warnings; preflight; recording
  and experiments.
- **Data contract:** the snapshot and command messages in `bridge/README.md`
  ("WebSocket protocol"). The dashboard must not need anything else from the robot.
- **Develop without the robot:** `python -m h2_diagnostics serve --replay <recording>` on any
  machine serves recorded data on the same protocol.

## Run it

```bash
cd dashboard && npm install            # once (Node 22+, via nvm)
npm run dev                            # http://localhost:5173
# data: a replay bridge on this machine (default ws://localhost:8765) ...
python -m h2_diagnostics serve --replay bridge/tests/data/sensors_20261112_150110.jsonl
# ... or the Thor: http://localhost:5173/?bridge=ws://172.16.68.113:8765
npm test                               # vitest
npm run typecheck                      # tsc, includes the snapshot contract check
```

## Layout

```
src/
├── contract/   snapshot.ts (types of every WS message) · snapshot.fixture.json (real message,
│               written by bridge/tests/test_contract.py) · fixture.ts (typed; the contract check)
├── bridge/     BridgeClient.ts (the only WebSocket: newest snapshot, status
│               connecting/live/stale/disconnected, reconnect, recorder commands) · useBridge.ts
├── robot/      jointMap.ts (L_knee -> left_knee_joint) · pose.ts (snapshot -> pose: rules, tested)
│               heat.ts (temperature -> colour, tested) · handPose.ts (Dex5 slot -> URDF link,
│               finger angles + colours, tested) · RobotScene.ts (three.js class: renderer,
│               camera, own animation loop, pulls client.latest, colours links, click picking)
│               RobotView.tsx (React wrapper: notices, legend, clicked-joint panel)
├── panels/     StatusStrip (connection, LIVE/REPLAY, battery, mode, board, topic dots) ·
│               WarningsPanel · HandPanel (per-finger temps + raw q, 16 pressure pads) ·
│               RecorderPanel (record/marker/stop) · status.ts, hands.ts, recorder.ts (logic, tested)
├── ui/         theme.ts (colours, warning-level colours, panel style, "?" marker)
└── App.tsx     shell: one BridgeClient in a React context; 3D fills the window, panels float over it
public/renders/ H2.urdf + meshes, Dex5 hands (served at /renders/...)
```

Rules: the dashboard only displays. Warnings come from the bridge; if a number is
missing, add it to the snapshot instead of computing it here. Joints map to the URDF **by
name** (`L_knee` -> `left_knee_joint`), never by URDF file order. React panels re-render per
snapshot (`useBridge()`); the 3D view reads `client.latest` each animation frame instead.

3D view facts: the URDF is Z-up, three.js Y-up (the robot sits in a group rotated -90° about
X; feet lifted to y=0). Pelvis tilt comes from the pelvis IMU's roll/pitch; yaw is dropped (it
drifts). `mode_pr != 0` freezes the pose (AB slots aren't angles); a null `q` is skipped.
Checked 2026-11-18 with a doctored replay: +knee bends back, -shoulder_pitch raises the arm
forward, L_ joints are on the robot's left. Mesh loading is counted by hand: LoadingManager's
onLoad fires early and is lost when StrictMode loads the same URLs twice.

Dex5 hands (2026-11-18): each Dex5 URDF is mounted on H2's `*_hand_link`. A "hands" toggle
(right column) shows the Dex5 hands, H2.urdf's own static hands, or both overlaid (to compare the
fit); default Dex5 only, remembered per browser (localStorage). The mount (`DEX5_MOUNT` in RobotScene.ts) was fitted by eye against that
placeholder (palms overlap, fingers curl to the same side); it is not a Unitree number. Slot ->
joint is inferred, not confirmed: URDF finger 1 = thumb, 2-5 = index..pinky, and within a finger
the slots follow the chain (roll, then 3 pitches), because the T2 ranges match the URDF limits.
Joints are found by child link (`Link_21L`): the left URDF misnames `Roll_41L` as `Link_41L`.
A q outside its URDF limits is skipped, not clamped (right thumb slot 17 reads ~2.9 vs 0..1.82).
Finger links take the motor's temperature colour; the thumb is grey (no temperature); fingers
can't be clicked (the hand panel has the detail).

What stays still (view panel, "fixed"): **ground** puts the lowest foot on the grid each update
(the body drops as the knees bend); **gantry** keeps the pelvis at standing height (legs hang).
**auto** follows the bridge's `support_raw` (summed |knee tau| with hysteresis,
`processing/support.py`; thresholds provisional, no ground recording yet) and falls back to
gantry while unknown. Only height changes: no odometry, so the robot never walks across the grid.
The IMU can't tell ground from gantry (same tilt and gravity either way); leg torque can.

Panels follow the same rule as the 3D colours: **every amber/red comes from a bridge warning id**
(`stale:<topic>`, `rate:<topic>`, `soc`, `cell_spread`, `board_temp:<i>`, `hand_<side>:temp:<i>`, ...;
see `health.py`), never from a threshold in the dashboard. Unconfirmed values (battery current, fsm,
`mode_machine`, hand `q`, hand supply, pressure) are shown with "?" and never coloured. Pressure
tiles use a provisional full-scale of 500 raw (`PRESSURE_FULL_RAW`) until T5. The snapshot's `t` is
the bridge's clock even in replay, so the strip shows a clock only when live.

Colours: each moving joint colours the link its motor carries (plus fixed children, e.g. the
camera). The 30–65 °C gradient only shows warmth; amber/red appear only when the
bridge sends a `temp:<joint>` warning, so the thresholds live in one place (`health.py`).

See `PLAN.md` for scope and schedule.
