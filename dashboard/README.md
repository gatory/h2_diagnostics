# Dashboard

The viewer half of the project, laid out for a **portrait (vertical) monitor**. It runs on
any computer on the robot's lab network and only talks to the bridge, never to the robot.

```
ROBOT (Thor)                                   ANY COMPUTER
bridge/  (h2diag serve --live)  ── WebSocket ──►  dashboard/  (this folder)
ws://<thor-ip>:8765                ◄── recorder commands only
```

Look and feel: `tesla.design.md` (repo root), inspired by Tesla's in-car screen. White canvas,
one accent colour (Electric Blue, only on Record), weights 400/500, 4px radius, no shadows.
Amber/red appear **only** when the bridge sends a warning.

## Run it

```bash
cd dashboard && npm install          # once (Node 22+)
npm run dev                          # http://localhost:5173

# data, either:
python -m h2_diagnostics serve --replay bridge/tests/data/sensors_20261112_150110.jsonl   # this machine
# ... or the Thor's live bridge: http://localhost:5173/?bridge=ws://172.16.68.113:8765

npm test                             # vitest (derive.test.ts)
npm run typecheck && npm run lint && npm run build
```

Full screen in the browser (F11) on the portrait monitor. Drag the robot to orbit, scroll to zoom.

## Screen, top to bottom

| Part | Shows | Source |
|---|---|---|
| Top bar | connection, LIVE/REPLAY, clock, battery % | `TopBar.tsx` |
| Robot | 3D H2 posed from joint angles + pelvis IMU, links coloured by motor temperature; status line; 3 big readouts (hottest motor, pack voltage, board temp) | `Hero.tsx`, `robot/scene.ts` |
| Alerts | the bridge's warnings, worst first (4 shown, "+N more") | `Alerts.tsx` |
| Hands | per finger motor temperatures (thumb: position only), 16 pressure pads (raw) | `HandCard.tsx` |
| Topics | receive rate per topic | `Topics.tsx` |
| Dock | Record / Mark / Stop (only controls the bridge's recorder) | `RecorderDock.tsx` |

## Code

- `src/types.ts`: the snapshot, as `main`'s bridge sends it
- `src/bridge.ts`: the one WebSocket (`Bridge` class + `useBridge()` hook); reconnects by itself
- `src/derive.ts`: every decision (status, colours, joint names), pure and unit-tested
- `src/robot/scene.ts`: three.js + urdf-loader; reads the newest snapshot each frame
- `src/components/`: one file per screen part
- `src/theme.css`: the design tokens as CSS variables

Models are served from `h2_renders/` (Vite's static folder): `/h2_description/H2.urdf`.
