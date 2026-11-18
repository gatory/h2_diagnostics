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
└── App.tsx     shell: one BridgeClient in a React context; panels plug in here
public/renders/ H2.urdf + meshes, Dex5 hands (served at /renders/...)
```

Rules: the dashboard only displays. Warnings come from the bridge; if a number is
missing, add it to the snapshot instead of computing it here. Joints map to the URDF **by
name** (`L_knee` -> `left_knee_joint`), never by URDF file order. React panels re-render per
snapshot (`useBridge()`); the 3D view reads `client.latest` each animation frame instead.

See `PLAN.md` for scope and schedule.
