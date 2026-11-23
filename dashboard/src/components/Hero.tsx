/**
 * The hero: robot name + one-line status over the 3D model, and three big readouts
 * under it (like the speed on a car screen). Status = worst bridge warning.
 */
import { useBridge } from "../bridge";
import { hottestJoint, jointLabel, jointLevel, maxReading, verdict, verdictText, worst } from "../derive";
import { RobotView } from "./RobotView";

const STATUS_CLASS = { ok: "", warn: "warn", fault: "error", nodata: "" } as const;
const STATUS_DOT = { ok: "ok", warn: "warn", fault: "error", nodata: "" } as const;

export function Hero() {
  const { snap } = useBridge();
  const v = verdict(snap);
  const body = snap?.body ?? null;
  const hot = hottestJoint(body);
  const hotLevel = hot && snap ? jointLevel(snap.warnings, hot.joint.name) : null;
  const board = maxReading(snap?.mainboard?.temps);
  const boardLevel = snap ? worst(snap.warnings, (id) => id.startsWith("board_temp:")) : null;
  const battery = snap?.battery;

  return (
    <section className="hero">
      <RobotView />
      <div className="hero-head">
        <div>
          <h1 className="hero-title">H2</h1>
          <div className="hero-sub">Unitree H2 EDU · Dex5 hands</div>
          <div className={`status-line ${STATUS_CLASS[v]}`}>
            <span className={`dot ${STATUS_DOT[v]}`} />
            {verdictText(snap)}
          </div>
        </div>
        <div className="chips">
          {body && body.mode_pr !== 0 && <span className="chip warn">Linkage mode AB · pose frozen</span>}
          {body && <span className="chip">Machine mode {body.mode_machine}<span className="unconfirmed">?</span></span>}
          {snap && !snap.joint_order_verified && <span className="chip">Joint order partly unverified</span>}
        </div>
      </div>

      <div className="readouts">
        <div className={`readout ${hotLevel ?? ""}`}>
          <div className="value">
            {hot ? hot.temp : "–"}
            <span className="unit">°C</span>
          </div>
          <div className="label">Hottest · {hot ? jointLabel(hot.joint.name) : "no data"}</div>
        </div>
        <div className="readout">
          <div className="value">
            {battery ? battery.voltage.toFixed(1) : "–"}
            <span className="unit">V</span>
          </div>
          <div className="label">Pack · cells Δ {battery?.cell_spread_mv ?? "–"} mV</div>
        </div>
        <div className={`readout ${boardLevel ?? ""}`}>
          <div className="value">
            {board ?? "–"}
            <span className="unit">°C</span>
          </div>
          <div className="label">Main board</div>
        </div>
      </div>
    </section>
  );
}
