/**
 * Snapshot -> what the screen shows. Plain functions (no React, no three.js), so
 * they're unit-tested in derive.test.ts.
 *
 * Rule: the dashboard never decides what is "too hot" or "too slow" itself. Amber and
 * red only ever come from the bridge's warnings (looked up by warning id); our own
 * numbers (the temperature gradient) only show HOW warm something is.
 */
import type { Body, Hand, Joint, Level, Snapshot, Warning } from "./types";

// ---- warnings ---------------------------------------------------------------------

const RANK: Record<Level, number> = { error: 0, warn: 1, info: 2 };

/** Worst level among warnings whose id matches; null = all clear. */
export function worst(warnings: Warning[], match: (id: string) => boolean = () => true): Level | null {
  let out: Level | null = null;
  for (const w of warnings) {
    if (match(w.id) && (out === null || RANK[w.level] < RANK[out])) out = w.level;
  }
  return out;
}

export type Verdict = "ok" | "warn" | "fault" | "nodata";

/** The one-word state of the whole robot (the hero's status line). */
export function verdict(snap: Snapshot | null): Verdict {
  if (!snap) return "nodata";
  const level = worst(snap.warnings);
  return level === "error" ? "fault" : level === "warn" ? "warn" : "ok";
}

export function verdictText(snap: Snapshot | null): string {
  if (!snap) return "Waiting for data";
  const errors = snap.warnings.filter((w) => w.level === "error").length;
  const warns = snap.warnings.filter((w) => w.level === "warn").length;
  if (errors) return `${errors} ${errors === 1 ? "fault" : "faults"}${warns ? ` · ${warns} warning${warns === 1 ? "" : "s"}` : ""}`;
  if (warns) return `${warns} warning${warns === 1 ? "" : "s"}`;
  return "All systems normal";
}

// ---- temperatures ----------------------------------------------------------------

/** Hotter of the two sensors; null when neither reads (0 means "no sensor"). */
export function motorTemp(temp: number[]): number | null {
  const valid = temp.filter((t) => t > 0);
  return valid.length ? Math.max(...valid) : null;
}

export function hottestJoint(body: Body | null): { joint: Joint; temp: number } | null {
  let best: { joint: Joint; temp: number } | null = null;
  for (const j of body?.joints ?? []) {
    const t = motorTemp(j.temp);
    if (t !== null && (!best || t > best.temp)) best = { joint: j, temp: t };
  }
  return best;
}

/** "L_shoulder_pitch" -> "L shoulder pitch". */
export function jointLabel(name: string): string {
  return name.replace(/_/g, " ");
}

// Colours for 3D links and motor cells (hex numbers so three.js can use them too).
export const COLOR = {
  cool: 0xc4c7cc, // at/below GRADIENT_C[0]: the model's resting grey
  warm: 0xdcbf9f, // at/above GRADIENT_C[1]: a soft sand, so it never looks like a warning
  nodata: 0x8e8e8e,
  warn: 0xf29d0a, // saturated amber: only from a bridge warning
  error: 0xe31937,
} as const;

/** Display range of the warmth gradient (°C). NOT a limit: limits live in health.py. */
export const GRADIENT_C: [number, number] = [30, 65];

export function heatColor(tempC: number | null, level?: Level | null): number {
  if (level === "error") return COLOR.error;
  if (level === "warn") return COLOR.warn;
  if (tempC === null) return COLOR.nodata;
  const [lo, hi] = GRADIENT_C;
  return mix(COLOR.cool, COLOR.warm, Math.min(1, Math.max(0, (tempC - lo) / (hi - lo))));
}

export function cssColor(hex: number): string {
  return `#${hex.toString(16).padStart(6, "0")}`;
}

function mix(a: number, b: number, f: number): number {
  const ch = (shift: number) => {
    const x = (a >> shift) & 0xff;
    const y = (b >> shift) & 0xff;
    return Math.round(x + (y - x) * f) << shift;
  };
  return ch(16) | ch(8) | ch(0);
}

// ---- body joints -> 3D -----------------------------------------------------------

/** Bridge name -> H2.urdf joint name: "L_knee" -> "left_knee_joint". Map by NAME, never order. */
export function urdfJointName(name: string): string {
  const n = name.startsWith("L_") ? "left_" + name.slice(2) : name.startsWith("R_") ? "right_" + name.slice(2) : name;
  return n.endsWith("_joint") ? n : n + "_joint";
}

/** Worst bridge warning about one body joint (temperature, status, limit, ...). */
export function jointLevel(warnings: Warning[], name: string): Level | null {
  return worst(warnings, (id) => id.endsWith(`:${name}`) && !id.startsWith("hand_"));
}

/** URDF joint name -> link colour, for every body joint. */
export function jointColors(snap: Snapshot): Map<string, number> {
  const out = new Map<string, number>();
  for (const j of snap.body?.joints ?? []) {
    out.set(urdfJointName(j.name), heatColor(motorTemp(j.temp), jointLevel(snap.warnings, j.name)));
  }
  return out;
}

/**
 * URDF joint name -> angle, or null when the angles can't be trusted for drawing.
 * mode_pr 1 (AB): ankle/waist slots hold raw motor positions, not angles.
 */
export function jointAngles(body: Body | null): Record<string, number> | null {
  if (!body || body.mode_pr !== 0) return null;
  const out: Record<string, number> = {};
  for (const j of body.joints) if (j.q !== null && Number.isFinite(j.q)) out[urdfJointName(j.name)] = j.q;
  return out;
}

// ---- hands ------------------------------------------------------------------------

export type Side = "left" | "right";

/** Slot groups from test T2 (docs/field_map.md). The thumb reports q only. */
export const FINGERS: { name: string; slots: number[] }[] = [
  { name: "Thumb", slots: [16, 17, 18, 19] },
  { name: "Index", slots: [0, 1, 2, 3] },
  { name: "Middle", slots: [4, 5, 6, 7] },
  { name: "Ring", slots: [8, 9, 10, 11] },
  { name: "Pinky", slots: [12, 13, 14, 15] },
];

/** Worst warning on one hand motor slot ("hand_left:temp:3", "hand_left:motorstate:3"). */
export function handMotorLevel(warnings: Warning[], side: Side, slot: number): Level | null {
  const re = new RegExp(`^hand_${side}:(temp|motorstate):${slot}$`);
  return worst(warnings, (id) => re.test(id));
}

/** Worst warning for a whole hand, including "no data". */
export function handLevel(warnings: Warning[], side: Side): Level | null {
  return worst(warnings, (id) => id.startsWith(`hand_${side}:`) || id === `missing:hand_${side}`);
}

/**
 * Raw pressure that fills a pad tile. PROVISIONAL: pads read about -57..+63 at rest and
 * the real scale comes from test T5. Chosen so resting noise stays faint.
 */
export const PRESSURE_FULL_RAW = 500;

export function padFill(hand: Hand, pad: number): number {
  const peak = Math.max(0, ...(hand.pressure[pad] ?? []).map((v) => Math.abs(v)));
  return Math.min(1, peak / PRESSURE_FULL_RAW);
}

export function handMaxTemp(hand: Hand): number | null {
  const temps = hand.motors.filter((m) => m.active).map((m) => motorTemp(m.temp)).filter((t): t is number => t !== null);
  return temps.length ? Math.max(...temps) : null;
}

// ---- topics + misc ---------------------------------------------------------------

const SHORT: Record<string, string> = {
  lowstate: "Body", secondary_imu: "Torso IMU", bmsstate: "Battery", mainboardstate: "Board",
};

/** "rt/lf/lowstate" -> "Body", "rt/dex5/left/state" -> "Left hand". */
export function topicLabel(topic: string): string {
  const hand = topic.match(/^rt\/dex5\/(left|right)\/state$/);
  if (hand) return hand[1] === "left" ? "Left hand" : "Right hand";
  const name = topic.replace(/^rt\/(lf\/)?/, "");
  return SHORT[name] ?? name;
}

export function topicLevel(warnings: Warning[], topic: string): Level | null {
  return worst(warnings, (id) => id === `stale:${topic}` || id === `rate:${topic}`);
}

/** Max of readings, ignoring 0 ("no sensor"); null when none. */
export function maxReading(values: number[] | undefined): number | null {
  const v = (values ?? []).filter((x) => x > 0);
  return v.length ? Math.max(...v) : null;
}

/** 74.5 -> "1:14". */
export function elapsedText(seconds: number): string {
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
