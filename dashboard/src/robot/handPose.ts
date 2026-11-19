/**
 * Dex5 hand snapshot -> finger angles and colours for the 3D hands. Pure (no three.js),
 * so it's unit-tested; RobotScene only applies the result.
 *
 * Slot -> URDF joint (inferred 2026-11-18, NOT confirmed on the robot):
 *  - Fingers: slots come four per finger (index 0-3 … pinky 12-15, thumb 16-19, from T2),
 *    and inside a finger they follow the URDF chain: base roll (spread), then three pitches.
 *    Evidence: in the T2 recording, the 1st slot is signed and within ±0.38 (the Roll
 *    limit), and the 3rd and 4th top out at 1.69 and 1.40 (the Pitch_x3 / Pitch_x4
 *    limits, 1.684 and 1.396). So q looks like radians.
 *  - URDF finger numbers: 1 = thumb (its base sits apart, with a yaw joint), 2-5 = index
 *    to pinky (2 is next to the thumb, 5 is set back and shorter).
 * Joints are found by their CHILD link, `Link_<finger><k><L|R>`, because the joint names
 * have a typo in the left URDF (`Link_41L` instead of `Roll_41L`).
 */
import type { Hand, Warning } from "../contract/snapshot";
import { motorLevels, type Side } from "../panels/hands";
import { heatColor, jointTemp } from "./heat";

export const DEX5_URDF: Record<Side, string> = {
  left: "/renders/dex5_hands/Dex5-URDF-L/Dex5-URDF-L.urdf",
  right: "/renders/dex5_hands/Dex5-URDF-R/Dex5-URDF-R.urdf",
};

/** URDF finger number for each group of four slots (index, middle, ring, pinky, thumb). */
const URDF_FINGER = [2, 3, 4, 5, 1];

/** How far past a URDF limit a q may be and still be drawn (rad). */
export const LIMIT_TOLERANCE = 0.05;

/** The Dex5 URDF link a hand motor slot moves, e.g. slot 0 on the left -> "Link_21L". */
export function dex5Link(side: Side, slot: number): string {
  const finger = URDF_FINGER[Math.floor(slot / 4)];
  return `Link_${finger}${(slot % 4) + 1}${side === "left" ? "L" : "R"}`;
}

/** Link name -> q for every slot with a finite q. */
export function handAngles(hand: Hand, side: Side): Map<string, number> {
  const out = new Map<string, number>();
  hand.motors.forEach((m, slot) => {
    if (m.q !== null && Number.isFinite(m.q)) out.set(dex5Link(side, slot), m.q);
  });
  return out;
}

/**
 * Whether to draw q at all. urdf-loader silently clamps to the limits, which would show a
 * believable but wrong finger; out-of-range values (e.g. the right thumb's slot 17 reads
 * 2.88 against 0..1.82, so its meaning differs) are skipped instead.
 */
export function drawable(q: number, lower: number, upper: number): boolean {
  return q >= lower - LIMIT_TOLERANCE && q <= upper + LIMIT_TOLERANCE;
}

/** Link name -> colour: warmth gradient, amber/red only from the bridge's hand warnings. */
export function handColors(hand: Hand, side: Side, warnings: Warning[]): Map<string, number> {
  const levels = motorLevels(warnings, side);
  const out = new Map<string, number>();
  hand.motors.forEach((m, slot) => {
    // Thumb slots report no temperature: NO_DATA grey.
    out.set(dex5Link(side, slot), heatColor(m.active ? jointTemp(m.temp) : null, levels.get(slot)));
  });
  return out;
}
