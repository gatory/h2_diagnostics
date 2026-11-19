/**
 * Motor temperature -> link colour. Pure, so it's unit-tested.
 *
 * Two layers, so the dashboard never decides what is "too hot" on its own:
 *  - a gradient (cool grey -> light orange) that only shows HOW WARM a motor is;
 *  - amber / red only when the BRIDGE has a `temp:<joint>` warning (health.py LIMITS).
 * Change the thresholds in health.py and the colours follow.
 */
import type { Joint, Snapshot, Warning, WarningLevel } from "../contract/snapshot";
import { LEVEL_COLOR } from "../ui/theme";
import { urdfJointName } from "./jointMap";

export const GRADIENT_C: [number, number] = [30, 65]; // display only, not a limit

const COOL = 0xd9dee4; // at/below 30 °C: the model's normal light grey
const WARM = 0xe8a868; // at/above 65 °C
const NO_DATA = 0x7d8691; // both sensors read 0: unknown

/** Hotter of the two sensors; null when neither reads (0 means "no sensor"). */
export function jointTemp(temp: number[]): number | null {
  const valid = temp.filter((t) => t > 0);
  return valid.length ? Math.max(...valid) : null;
}

/** Joint name -> level of the bridge's temperature warning for it. */
export function tempWarnings(warnings: Warning[]): Map<string, WarningLevel> {
  const out = new Map<string, WarningLevel>();
  for (const w of warnings) if (w.id.startsWith("temp:")) out.set(w.id.slice(5), w.level);
  return out;
}

export function heatColor(tempC: number | null, level?: WarningLevel): number {
  if (level === "warn" || level === "error") return LEVEL_COLOR[level];
  if (tempC === null) return NO_DATA;
  const [lo, hi] = GRADIENT_C;
  return mix(COOL, WARM, Math.min(1, Math.max(0, (tempC - lo) / (hi - lo))));
}

/** URDF joint name -> colour for every body joint in the snapshot. */
export function jointColors(snap: Snapshot): Map<string, number> {
  const out = new Map<string, number>();
  if (!snap.body) return out;
  const levels = tempWarnings(snap.warnings);
  for (const j of snap.body.joints) {
    out.set(urdfJointName(j.name), heatColor(jointTemp(j.temp), levels.get(j.name)));
  }
  return out;
}

/** The snapshot's joint for a URDF joint name (what the user clicked). */
export function findJoint(snap: Snapshot | null, urdfName: string): Joint | undefined {
  return snap?.body?.joints.find((j) => urdfJointName(j.name) === urdfName);
}

function mix(a: number, b: number, f: number): number {
  const ch = (shift: number) => {
    const x = (a >> shift) & 0xff;
    const y = (b >> shift) & 0xff;
    return Math.round(x + (y - x) * f) << shift;
  };
  return ch(16) | ch(8) | ch(0);
}
