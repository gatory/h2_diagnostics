/**
 * Snapshot -> what the status strip shows. Pure, so it's unit-tested.
 *
 * Every colour comes from the bridge's warnings (looked up by warning id), never
 * from thresholds of our own: the dashboard only displays (one pipeline).
 * Warning ids are defined in bridge/h2_diagnostics/processing/health.py.
 */
import type { Snapshot, Warning, WarningLevel } from "../contract/snapshot";

const RANK: Record<WarningLevel, number> = { error: 0, warn: 1, info: 2 };

/** Worst level among warnings whose id matches; null = all clear. */
export function worstLevel(warnings: Warning[], match: (id: string) => boolean): WarningLevel | null {
  let worst: WarningLevel | null = null;
  for (const w of warnings) {
    if (match(w.id) && (worst === null || RANK[w.level] < RANK[worst])) worst = w.level;
  }
  return worst;
}

const SHORT: Record<string, string> = {
  lowstate: "body", secondary_imu: "torso imu", bmsstate: "bms", mainboardstate: "board",
};

/** Strip label: "rt/lf/lowstate" -> "body", "rt/dex5/left/state" -> "hand L" (full name on hover). */
export function shortTopic(topic: string): string {
  const hand = topic.match(/^rt\/dex5\/(left|right)\/state$/);
  if (hand) return `hand ${hand[1] === "left" ? "L" : "R"}`;
  const name = topic.replace(/^rt\/(lf\/)?/, "");
  return SHORT[name] ?? name;
}

export interface TopicDot {
  topic: string;
  label: string;
  level: WarningLevel | null;
  text: string; // "20.0/20 Hz", "silent", ...
}

export function topicDots(snap: Snapshot): TopicDot[] {
  return Object.entries(snap.topics)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([topic, t]) => ({
      topic,
      label: shortTopic(topic),
      level: worstLevel(snap.warnings, (id) => id === `stale:${topic}` || id === `rate:${topic}`),
      text: t.hz === null ? "measuring…" : `${t.hz.toFixed(0)}${t.expected_hz ? `/${t.expected_hz}` : ""} Hz`,
    }));
}

/** Ids per strip section: which warnings colour which part of the strip. */
export const SECTION_IDS = {
  battery: (id: string) => id === "soc" || id === "cell_spread" || id === "battery_temp" || id === "missing:battery",
  board: (id: string) => id.startsWith("board_temp:") || id === "missing:mainboard",
  comms: (id: string) => id.startsWith("stale:") || id.startsWith("rate:") || id.startsWith("missing:"),
};

/** Max of readings, ignoring 0 ("no sensor"); null when none. */
export function maxReading(values: number[]): number | null {
  const v = values.filter((x) => x > 0);
  return v.length ? Math.max(...v) : null;
}

/**
 * The bridge's clock, live only. In replay `t` is still the bridge's "now", not the
 * recording's time, so showing it would mislead (the recording's own time isn't in
 * the snapshot yet).
 */
export function clockText(snap: Snapshot): string | null {
  if (snap.source !== "live") return null;
  const d = new Date(snap.t * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
