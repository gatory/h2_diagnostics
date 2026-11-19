/**
 * Recording controls: what the panel can do and how to describe the bridge's replies.
 * Pure, so it's unit-tested. Commands go through BridgeClient.send() and only
 * control the bridge's recorder (sessions are written on the Thor); nothing
 * reaches the robot.
 */
import type { ConnectionStatus } from "../bridge/BridgeClient";
import type { Ack, Command, RecorderStatus } from "../contract/snapshot";

export type RecorderMode = "unavailable" | "idle" | "recording";

export function recorderMode(status: ConnectionStatus, rec: RecorderStatus | undefined): RecorderMode {
  if (status !== "live" || !rec) return "unavailable"; // not connected, or bridge without a recorder
  return rec.recording ? "recording" : "idle";
}

/** File-name friendly default, e.g. "session_1432". The bridge adds the date. */
export function defaultName(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `session_${pad(now.getHours())}${pad(now.getMinutes())}`;
}

export function startCommand(name: string, notes: string): Command {
  const n = name.trim() || defaultName();
  return notes.trim() ? { cmd: "record_start", name: n, notes: notes.trim() } : { cmd: "record_start", name: n };
}

export function markerCommand(text: string): Command | null {
  const t = text.trim();
  return t ? { cmd: "marker", text: t } : null;
}

/** One line about the last reply, or null if it isn't about the recorder. */
export function ackText(ack: Ack | null): { ok: boolean; text: string } | null {
  if (!ack) return null;
  if (!ack.ok) return { ok: false, text: `${ack.cmd ?? "command"} failed: ${ack.error ?? "not recording"}` };
  switch (ack.cmd) {
    case "record_start":
      return { ok: true, text: `recording to ${ack.file}` };
    case "record_stop":
      return { ok: true, text: ack.file ? `saved ${ack.file}` : "nothing was recording" };
    case "marker":
      return { ok: true, text: "marker added" };
    default:
      return null;
  }
}

export function elapsedText(seconds: number): string {
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
