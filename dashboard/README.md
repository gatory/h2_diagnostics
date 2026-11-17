# Dashboard (not started; Dashboard phase, Dec 7–20)

The viewer half of the project. It runs on **any computer** on the same network as
the robot's Thor and only talks to the bridge, never to the robot directly.

```
ROBOT (Thor)                                   ANY COMPUTER
bridge/  (h2diag serve --live)  ── WebSocket ──►  dashboard/  (this folder)
ws://<thor-ip>:8765                ◄── recorder commands only
```

- **Planned stack:** TypeScript + Vite + three.js + urdf-loader, opened in its own window.
- **Main screen:** live 3D robot colored by motor temperature; Dex5 hands in the lower
  corners; status strip (battery, mode, topic health); warnings; preflight; recording
  and experiments.
- **Data contract:** the snapshot and command messages in `bridge/README.md`
  ("WebSocket protocol"). The dashboard must not need anything else from the robot.
- **Develop without the robot:** `python -m h2diag serve --replay <recording>` on any
  machine serves recorded data on the same protocol.

See `PLAN.md` for scope and schedule.
