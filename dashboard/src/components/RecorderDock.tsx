/**
 * Bottom dock (Tesla's "Ask a Question" bar): start/stop a recording, drop markers.
 * Commands only reach the bridge's recorder (sessions are written on the Thor);
 * nothing here can reach the robot. Record is the one Electric Blue button on screen.
 */
import { useState, type FormEvent } from "react";
import { useBridge, useBridgeInstance } from "../bridge";
import { elapsedText } from "../derive";
import type { Ack } from "../types";

export function RecorderDock() {
  const bridge = useBridgeInstance();
  const { conn, snap, ack } = useBridge();
  const rec = snap?.recorder;
  const usable = conn === "live" && rec !== undefined;
  const [name, setName] = useState("");
  const [marker, setMarker] = useState("");

  const start = (e: FormEvent) => {
    e.preventDefault();
    const n = name.trim() || defaultName();
    if (bridge.send({ cmd: "record_start", name: n })) setName("");
  };
  const mark = (e: FormEvent) => {
    e.preventDefault();
    const text = marker.trim();
    if (text && bridge.send({ cmd: "marker", text })) setMarker("");
  };
  const reply = ackText(ack);

  return (
    <footer className="dock">
      {rec?.recording ? (
        <>
          <div className="status">
            <span className="rec-dot" />
            Recording {rec.name} · {elapsedText(rec.elapsed_s ?? 0)}
          </div>
          <form onSubmit={mark}>
            <input className="input" placeholder="Marker, before each action" value={marker}
                   onChange={(e) => setMarker(e.target.value)} />
            <button className="btn btn-secondary" type="submit" disabled={!usable}>Mark</button>
            <button className="btn btn-secondary" type="button" disabled={!usable}
                    onClick={() => bridge.send({ cmd: "record_stop" })}>Stop</button>
          </form>
        </>
      ) : (
        <form onSubmit={start}>
          <input className="input" disabled={!usable} value={name} onChange={(e) => setName(e.target.value)}
                 placeholder={usable ? "Session name, e.g. t5 pressure" : rec === undefined && conn === "live"
                   ? "This bridge has no recorder" : "Recording needs the bridge"} />
          <button className="btn btn-primary" type="submit" disabled={!usable}>Record</button>
        </form>
      )}
      {reply && <div className={`reply${reply.ok ? "" : " bad"}`}>{reply.text}</div>}
    </footer>
  );
}

function defaultName(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `session_${pad(now.getHours())}${pad(now.getMinutes())}`;
}

function ackText(ack: Ack | null): { ok: boolean; text: string } | null {
  if (!ack) return null;
  if (!ack.ok) return { ok: false, text: `${ack.cmd ?? "Command"} failed: ${ack.error ?? "not recording"}` };
  if (ack.cmd === "record_start") return { ok: true, text: `Recording to ${ack.file}` };
  if (ack.cmd === "record_stop") return { ok: true, text: ack.file ? `Saved ${ack.file}` : "Nothing was recording" };
  if (ack.cmd === "marker") return { ok: true, text: "Marker added" };
  return null;
}
