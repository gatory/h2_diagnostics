import { describe, expect, it } from "vitest";
import { ackText, defaultName, elapsedText, markerCommand, recorderMode, startCommand } from "./recorder";

describe("recorder controls", () => {
  it("is only usable while live data flows and the bridge has a recorder", () => {
    expect(recorderMode("live", { recording: false })).toBe("idle");
    expect(recorderMode("live", { recording: true, name: "a", file: "f", elapsed_s: 1 })).toBe("recording");
    expect(recorderMode("stale", { recording: false })).toBe("unavailable");
    expect(recorderMode("live", undefined)).toBe("unavailable");
  });

  it("builds the bridge's commands, trimming and defaulting", () => {
    expect(startCommand("  t5 pressure ", "")).toEqual({ cmd: "record_start", name: "t5 pressure" });
    expect(startCommand("", " right hand ")).toEqual({ cmd: "record_start", name: defaultName(), notes: "right hand" });
    expect(markerCommand("  press index ")).toEqual({ cmd: "marker", text: "press index" });
    expect(markerCommand("   ")).toBeNull();
    expect(defaultName(new Date(2026, 10, 18, 9, 5))).toBe("session_0905");
  });

  it("describes the bridge's replies", () => {
    expect(ackText({ type: "ack", cmd: "record_start", ok: true, file: "x.jsonl" })).toEqual({ ok: true, text: "recording to x.jsonl" });
    expect(ackText({ type: "ack", cmd: "record_stop", ok: true, file: null })?.text).toBe("nothing was recording");
    expect(ackText({ type: "ack", cmd: "marker", ok: false })).toEqual({ ok: false, text: "marker failed: not recording" });
    expect(ackText({ type: "ack", cmd: null, ok: false, error: "bad json" })?.ok).toBe(false);
    expect(ackText(null)).toBeNull();
  });

  it("formats elapsed time", () => {
    expect(elapsedText(0)).toBe("0:00");
    expect(elapsedText(75.9)).toBe("1:15");
  });
});
