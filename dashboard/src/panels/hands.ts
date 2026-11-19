/**
 * Dex5 hand -> what a hand panel shows. Pure, so it's unit-tested.
 *
 * Slot layout from test T2 (2026-11-17, docs/field_map.md): four motors per finger,
 * index 0-3, middle 4-7, ring 8-11, pinky 12-15, thumb 16-19. The thumb reports q
 * only (no temperature/status), so the bridge marks it inactive.
 * Colours: gradient for warmth, amber/red only from the bridge's hand warnings.
 */
import type { Hand, Snapshot, Warning, WarningLevel } from "../contract/snapshot";
import { worstLevel } from "./status";

export type Side = "left" | "right";

export const FINGERS: { name: string; slots: number[] }[] = [
  { name: "index", slots: [0, 1, 2, 3] },
  { name: "middle", slots: [4, 5, 6, 7] },
  { name: "ring", slots: [8, 9, 10, 11] },
  { name: "pinky", slots: [12, 13, 14, 15] },
  { name: "thumb", slots: [16, 17, 18, 19] },
];

/**
 * Raw pressure that fills a pad tile completely. PROVISIONAL: pads read about
 * -57..+63 at rest and nobody has pressed one yet (test T5 sets the real scale).
 * Chosen so resting noise stays dim.
 */
export const PRESSURE_FULL_RAW = 500;

/** Worst warning for this hand (anything under hand_<side>:, or the hand missing). */
export function handLevel(warnings: Warning[], side: Side): WarningLevel | null {
  return worstLevel(warnings, (id) => id.startsWith(`hand_${side}:`) || id === `missing:hand_${side}`);
}

/** Motor slot -> worst warning on that motor (temperature or status). */
export function motorLevels(warnings: Warning[], side: Side): Map<number, WarningLevel> {
  const out = new Map<number, WarningLevel>();
  const re = new RegExp(`^hand_${side}:(temp|motorstate):(\\d+)$`);
  for (const w of warnings) {
    const m = w.id.match(re);
    if (!m) continue;
    const slot = Number(m[2]);
    const prev = out.get(slot);
    if (!prev || (prev !== "error" && w.level === "error")) out.set(slot, w.level);
  }
  return out;
}

export interface PadTile {
  pad: number;
  peak: number; // largest |raw value| of the pad's cells
  fill: number; // 0..1 of PRESSURE_FULL_RAW
  lost: boolean;
}

export function padTiles(hand: Hand): PadTile[] {
  return hand.pressure.map((cells, pad) => {
    const peak = Math.max(0, ...cells.map((v) => Math.abs(v)));
    return { pad, peak, fill: Math.min(1, peak / PRESSURE_FULL_RAW), lost: hand.pads_lost[pad] !== 0 };
  });
}

export function handOf(snap: Snapshot | null, side: Side): Hand | null {
  return snap?.hands[side] ?? null;
}
