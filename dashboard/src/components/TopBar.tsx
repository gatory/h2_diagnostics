/**
 * Top bar, like the car's: connection on the left, clock in the middle, battery right.
 * Battery colour comes from the bridge's battery warnings (soc, cell_spread, battery_temp).
 */
import { useEffect, useState } from "react";
import { useBridge, type Conn } from "../bridge";
import { worst } from "../derive";
import type { Snapshot } from "../types";

const CONN: Record<Conn, { text: string; dot: string }> = {
  live: { text: "Connected", dot: "ok" },
  stale: { text: "No data", dot: "warn" },
  connecting: { text: "Connecting", dot: "" },
  offline: { text: "Bridge offline", dot: "error" },
};

const BATTERY_IDS = new Set(["soc", "cell_spread", "battery_temp", "missing:battery"]);

export function TopBar() {
  const { conn, snap } = useBridge();
  const c = CONN[conn];
  return (
    <header className="topbar">
      <div className="conn">
        <span className={`dot ${c.dot}`} />
        {c.text}
        {snap && <span className="tag">{snap.source === "live" ? "LIVE" : "REPLAY"}</span>}
      </div>
      <Clock />
      <div className="right">
        <Battery snap={snap} />
      </div>
    </header>
  );
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return <div className="clock">{now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>;
}

function Battery({ snap }: { snap: Snapshot | null }) {
  const b = snap?.battery;
  if (!b) return <span className="muted">Battery –</span>;
  const level = worst(snap.warnings, (id) => BATTERY_IDS.has(id)) ?? "";
  // Pack voltage is a big readout under the robot; here just the charge, like a car.
  return (
    <>
      <div className={`battery ${level}`} aria-label={`battery ${b.soc}%`}
           title={`${b.voltage.toFixed(1)} V · current ${b.current_raw}? (probably mA, negative = discharge; unconfirmed)`}>
        <div className="fill" style={{ width: `${Math.max(0, Math.min(100, b.soc))}%` }} />
      </div>
      <span>{b.soc}%</span>
    </>
  );
}
