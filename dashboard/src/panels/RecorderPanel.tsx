/**
 * Record / stop / marker. Sessions are written by the bridge on the Thor, so a
 * Wi-Fi dropout doesn't leave gaps. Commands only reach the recorder, never the robot.
 */
import { useState, type CSSProperties, type FormEvent } from "react";
import { useBridge, useBridgeClient } from "../bridge/useBridge";
import { COLORS } from "../ui/theme";
import { ackText, elapsedText, markerCommand, recorderMode, startCommand } from "./recorder";

export function RecorderPanel() {
  const client = useBridgeClient();
  const { status, latest, lastAck } = useBridge();
  const rec = latest?.recorder;
  const mode = recorderMode(status, rec);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [marker, setMarker] = useState("");
  const reply = ackText(lastAck);

  const start = (e: FormEvent) => {
    e.preventDefault();
    if (client.send(startCommand(name, notes))) {
      setName("");
      setNotes("");
    }
  };
  const addMarker = (e: FormEvent) => {
    e.preventDefault();
    const cmd = markerCommand(marker);
    if (cmd && client.send(cmd)) setMarker("");
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ color: COLORS.dim }}>recording</span>
        {rec?.recording && (
          <span style={{ color: "#e5484d", fontWeight: 600 }}>
            ● {rec.name} · {elapsedText(rec.elapsed_s)}
          </span>
        )}
      </div>

      {mode === "unavailable" && (
        <div style={{ color: COLORS.dim }}>{status === "live" ? "bridge has no recorder" : "waiting for the bridge"}</div>
      )}

      {mode === "idle" && (
        <form onSubmit={start} style={{ display: "grid", gap: 6 }}>
          <input placeholder="name, e.g. t5 pressure" value={name} onChange={(e) => setName(e.target.value)} style={INPUT} />
          <input placeholder="notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} style={INPUT} />
          <button type="submit" style={{ ...BUTTON, background: "#b4232a" }}>● Record</button>
        </form>
      )}

      {mode === "recording" && (
        <div style={{ display: "grid", gap: 6 }}>
          <form onSubmit={addMarker} style={{ display: "flex", gap: 6 }}>
            <input placeholder="marker, before each action" value={marker} onChange={(e) => setMarker(e.target.value)}
                   style={{ ...INPUT, flex: 1 }} />
            <button type="submit" style={{ ...BUTTON, background: "#2f5fb3" }}>Mark</button>
          </form>
          <button onClick={() => client.send({ cmd: "record_stop" })} style={{ ...BUTTON, background: "#3a434d" }}>
            ■ Stop
          </button>
        </div>
      )}

      {reply && (
        <div style={{ marginTop: 6, fontSize: 11, color: reply.ok ? COLORS.dim : "#e5484d", wordBreak: "break-all" }}>
          {reply.ok ? "✓ " : "✗ "}
          {reply.text}
        </div>
      )}
    </div>
  );
}

const INPUT: CSSProperties = {
  background: "#0b0e11", color: COLORS.text, border: `1px solid ${COLORS.border}`, borderRadius: 4,
  padding: "5px 7px", font: "12px system-ui", minWidth: 0,
};
const BUTTON: CSSProperties = {
  color: "white", border: "none", borderRadius: 4, padding: "5px 10px", font: "600 12px system-ui", cursor: "pointer",
};
