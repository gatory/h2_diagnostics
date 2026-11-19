/**
 * The 3D robot panel: a React wrapper around RobotScene.
 * React creates/disposes the scene, keeps which joint is selected, and draws the
 * overlays (joint panel, notices, legend, view options). The scene pulls snapshots by itself.
 */
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useBridge, useBridgeClient } from "../bridge/useBridge";
import { HAND_PANEL_HEIGHT } from "../panels/HandPanel";
import { STRIP_HEIGHT } from "../panels/StatusStrip";
import { COLORS, hex, PANEL, UNCONFIRMED } from "../ui/theme";
import { findJoint, GRADIENT_C, heatColor, jointTemp, tempWarnings } from "./heat";
import { poseFromSnapshot, resolveFrame, type FrameChoice } from "./pose";
import { RobotScene, type HandSet } from "./RobotScene";

type LoadState = { kind: "loading" } | { kind: "ready"; handErrors: string[] } | { kind: "error"; message: string };
type HandsShown = Record<HandSet, boolean>;

/** Which hands this viewer last chose. Browser storage: a per-viewer convenience only. */
const HANDS_KEY = "h2dash.hands";
const DEFAULT_HANDS: HandsShown = { dex5: true, h2: false };
function savedHands(): HandsShown {
  try {
    return { ...DEFAULT_HANDS, ...JSON.parse(localStorage.getItem(HANDS_KEY) ?? "{}") };
  } catch {
    return DEFAULT_HANDS;
  }
}
const FRAME_KEY = "h2dash.frame";
const FRAMES: FrameChoice[] = ["auto", "ground", "gantry"];
function savedFrame(): FrameChoice {
  try {
    const f = localStorage.getItem(FRAME_KEY);
    return FRAMES.includes(f as FrameChoice) ? (f as FrameChoice) : "auto";
  } catch {
    return "auto";
  }
}
function remember(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage blocked: the choice still works for this visit */
  }
}

export function RobotView() {
  const client = useBridgeClient();
  const mount = useRef<HTMLDivElement>(null);
  const scene = useRef<RobotScene | null>(null);
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [selected, setSelected] = useState<string | null>(null); // URDF joint name
  const [hands, setHands] = useState<HandsShown>(savedHands);
  const [frame, setFrame] = useState<FrameChoice>(savedFrame);

  useEffect(() => {
    const s = new RobotScene(mount.current!, () => client.latest).start();
    s.onSelect = setSelected;
    scene.current = s;
    let alive = true; // StrictMode mounts twice in dev: ignore the first scene's promise
    s.load().then(
      () => alive && setLoad({ kind: "ready", handErrors: [...s.handErrors] }),
      (e: Error) => alive && setLoad({ kind: "error", message: e.message }),
    );
    return () => {
      alive = false;
      s.dispose();
    };
  }, [client]);

  // Push the toggles into the scene (also after a new scene is created), and remember them.
  useEffect(() => {
    for (const set of ["h2", "dex5"] as const) scene.current?.setHandsVisible(set, hands[set]);
    remember(HANDS_KEY, JSON.stringify(hands));
  }, [hands, client]);
  useEffect(() => {
    scene.current?.setFrame(frame);
    remember(FRAME_KEY, frame);
  }, [frame, client]);

  const close = () => {
    scene.current?.select(null);
    setSelected(null);
  };

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div ref={mount} style={{ position: "absolute", inset: 0 }} />
      <Notices load={load} />
      <div style={RIGHT_COLUMN}>
        <Legend />
        <ViewOptions hands={hands} onHands={setHands} frame={frame} onFrame={setFrame} />
        {selected && <JointPanel urdfJoint={selected} onClose={close} />}
      </div>
    </div>
  );
}

/** Why the picture might be wrong: loading, frozen pose, unverified joint order. */
function Notices({ load }: { load: LoadState }) {
  const { latest } = useBridge();
  const frozen = latest ? poseFromSnapshot(latest).frozen : "waiting for the bridge";
  const lines = [
    load.kind === "loading" && "loading robot model…",
    load.kind === "error" && `model failed: ${load.message}`,
    ...(load.kind === "ready" ? load.handErrors.map((e) => `Dex5 hand not loaded (${e})`) : []),
    frozen && `pose not shown: ${frozen}`,
    latest && !latest.joint_order_verified && "joint order not fully verified (wrist slots 20/27)",
  ].filter(Boolean);
  if (!lines.length) return null;
  return (
    <div style={{ position: "absolute", bottom: 16, left: "50%", transform: "translateX(-50%)",
                  color: COLORS.notice, font: "13px system-ui", textAlign: "center", pointerEvents: "none" }}>
      {lines.map((l) => <div key={String(l)}>{l}</div>)}
    </div>
  );
}

/** What the link colours mean. The thresholds behind amber/red live in the bridge. */
function Legend() {
  const [lo, hi] = GRADIENT_C;
  const stops = [lo, (lo + hi) / 2, hi].map((t) => hex(heatColor(t)));
  const swatch = (c: number): CSSProperties => ({ display: "inline-block", width: 10, height: 10,
                                                  background: hex(c), marginRight: 4, borderRadius: 2 });
  return (
    <div style={{ ...PANEL, position: "relative", fontSize: 12, flexShrink: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        {lo} °C
        <span style={{ width: 90, height: 8, borderRadius: 4,
                       background: `linear-gradient(to right, ${stops.join(",")})` }} />
        {hi} °C
      </div>
      <div style={{ marginTop: 4 }}>
        <span style={swatch(heatColor(0, "warn"))} />warn
        <span style={{ ...swatch(heatColor(0, "error")), marginLeft: 10 }} />error
        <span style={{ ...swatch(heatColor(null)), marginLeft: 10 }} />no reading
      </div>
      <div style={{ marginTop: 2, opacity: 0.6 }}>warn/error from the bridge's health checks</div>
      <div style={{ marginTop: 2, opacity: 0.6 }}>finger angles: hand q read as rad{UNCONFIRMED} · thumb grey (no temp)</div>
    </div>
  );
}

/**
 * View options: which hands to draw (H2.urdf's own, Dex5, or both overlaid as a fit check),
 * and what stays still (floor or pelvis). Auto shows what the bridge's estimate says.
 */
function ViewOptions({ hands, onHands, frame, onFrame }: {
  hands: HandsShown; onHands: (h: HandsShown) => void; frame: FrameChoice; onFrame: (f: FrameChoice) => void;
}) {
  const { latest } = useBridge();
  const support = latest?.support_raw;
  const box = (set: HandSet, label: string, title: string) => (
    <label title={title} style={OPTION}>
      <input type="checkbox" checked={hands[set]} onChange={(e) => onHands({ ...hands, [set]: e.target.checked })} />
      {label}
    </label>
  );
  const radio = (f: FrameChoice) => (
    <label key={f} style={OPTION}>
      <input type="radio" name="frame" checked={frame === f} onChange={() => onFrame(f)} />
      {f}
    </label>
  );
  const load = support?.knee_load_nm;
  return (
    <div style={{ ...PANEL, position: "relative", fontSize: 12, display: "grid", gap: 4, pointerEvents: "auto", flexShrink: 0 }}>
      <div style={{ display: "flex", gap: 10 }}>
        <span style={ROW_LABEL}>hands</span>
        {box("dex5", "Dex5", "Dex5 models: fingers follow hand q, coloured per finger motor")}
        {box("h2", "H2 URDF", "H2.urdf's own static hands (no finger joints)")}
      </div>
      <div style={{ display: "flex", gap: 10 }} title="ground: feet stay on the floor · gantry: pelvis stays still, legs hang">
        <span style={ROW_LABEL}>fixed</span>
        {FRAMES.map(radio)}
      </div>
      <div style={{ color: COLORS.dim }} title="bridge estimate from summed knee torque; thresholds provisional until a recording on the ground">
        {frame === "auto" ? `showing ${resolveFrame(latest, "auto")}` : "manual"} · bridge says{" "}
        {support?.state ?? "unknown"}{UNCONFIRMED}{load != null && ` (knees ${load.toFixed(1)} N·m)`}
      </div>
    </div>
  );
}
const OPTION: CSSProperties = { display: "flex", alignItems: "center", gap: 3, cursor: "pointer" };
const ROW_LABEL: CSSProperties = { color: COLORS.dim, width: 38 };

/** Live values of the clicked joint (re-renders with every snapshot). */
function JointPanel({ urdfJoint, onClose }: { urdfJoint: string; onClose: () => void }) {
  const { latest } = useBridge();
  const j = findJoint(latest, urdfJoint);
  const level = j && latest ? tempWarnings(latest.warnings).get(j.name) : undefined;
  const fmt = (v: number | null, digits = 3) => (v === null ? "invalid" : v.toFixed(digits));
  const deg = (v: number | null) => (v === null ? "" : ` (${((v * 180) / Math.PI).toFixed(1)}°)`);
  const rows: [string, string][] = j
    ? [
        ["slot", String(j.i)],
        ["q", `${fmt(j.q)} rad${deg(j.q)}`],
        ["dq", `${fmt(j.dq)} rad/s`],
        ["τ est", `${fmt(j.tau)} N·m`],
        ["temp", `${j.temp.join(" / ")} °C` + (jointTemp(j.temp) === null ? " (no reading)" : "")],
        ["motorstate", j.motorstate === 0 ? "0 (ok)" : `${j.motorstate} (error bits)`],
        ["mode", String(j.mode)],
        ["supply", j.vol === null ? "invalid" : `${j.vol} V`],
      ]
    : [];
  return (
    <div style={{ ...PANEL, position: "relative", pointerEvents: "auto", minHeight: 0, overflowY: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <strong>{j?.name ?? urdfJoint}</strong>
        <button onClick={onClose} aria-label="close"
                style={{ background: "none", border: "none", color: COLORS.dim, cursor: "pointer" }}>✕</button>
      </div>
      {level && <div style={{ color: hex(heatColor(0, level)), marginBottom: 6 }}>temperature {level}</div>}
      {j ? (
        <table style={{ borderSpacing: "8px 2px", marginLeft: -8, font: "12px monospace" }}>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}><td style={{ opacity: 0.6 }}>{k}</td><td>{v}</td></tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div style={{ opacity: 0.7 }}>no data for this joint yet</div>
      )}
    </div>
  );
}

/**
 * Right-hand stack: legend, hand toggles, clicked joint. It stops above the right hand
 * panel; if space runs out, the joint panel scrolls. Clicks pass through the gaps.
 */
const RIGHT_COLUMN: CSSProperties = {
  position: "absolute", top: STRIP_HEIGHT + 12, right: 16, bottom: 16 + HAND_PANEL_HEIGHT + 8, width: 250,
  display: "flex", flexDirection: "column", gap: 8, pointerEvents: "none",
};
