import { describe, expect, it } from "vitest";
import { fixture } from "../contract/fixture";
import type { Snapshot, Warning } from "../contract/snapshot";
import { clockText, maxReading, SECTION_IDS, shortTopic, topicDots, worstLevel } from "./status";

const w = (id: string, level: Warning["level"]): Warning => ({ id, level, subsystem: "x", msg: id });

describe("status strip logic", () => {
  it("picks the worst matching level, null when clear", () => {
    const ws = [w("soc", "warn"), w("cell_spread", "error"), w("temp:L_knee", "error")];
    expect(worstLevel(ws, SECTION_IDS.battery)).toBe("error");
    expect(worstLevel([w("soc", "warn")], SECTION_IDS.battery)).toBe("warn");
    expect(worstLevel(ws, SECTION_IDS.board)).toBeNull();
  });

  it("shortens topic names", () => {
    expect(shortTopic("rt/lf/lowstate")).toBe("body");
    expect(shortTopic("rt/lowstate")).toBe("body"); // old recordings: same label
    expect(shortTopic("rt/lf/secondary_imu")).toBe("torso imu");
    expect(shortTopic("rt/odd/topic")).toBe("odd/topic");
    expect(shortTopic("rt/dex5/right/state")).toBe("hand R");
  });

  it("colours a topic dot only from the bridge's stale:/rate: warnings", () => {
    const quiet = topicDots(fixture);
    expect(quiet).toHaveLength(Object.keys(fixture.topics).length);
    expect(quiet.every((d) => d.level === null)).toBe(true);
    const snap: Snapshot = { ...fixture, warnings: [w("stale:rt/lf/bmsstate", "error"), w("rate:rt/lf/bmsstate", "warn")] };
    const bms = topicDots(snap).find((d) => d.topic === "rt/lf/bmsstate")!;
    expect(bms.level).toBe("error");
    expect(bms.text).toMatch(/\/20 Hz$/); // measured / expected
  });

  it("ignores zero readings (no sensor)", () => {
    expect(maxReading([30, 0, 22])).toBe(30);
    expect(maxReading([0, 0])).toBeNull();
  });

  it("shows a clock only live (in replay t is the bridge's now, not the recording's time)", () => {
    expect(clockText({ ...fixture, source: "replay" })).toBeNull();
    expect(clockText({ ...fixture, source: "live" })).toMatch(/^\d\d:\d\d:\d\d$/);
  });
});
