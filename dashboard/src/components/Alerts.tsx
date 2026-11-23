/**
 * The bridge's warnings, most severe first (the bridge sorts them). Shows the first
 * MAX_ROWS so the layout never jumps; the rest are summed up in one line.
 */
import { useBridge } from "../bridge";

const MAX_ROWS = 4;

export function Alerts() {
  const { snap } = useBridge();
  const warnings = (snap?.warnings ?? []).filter((w) => w.level !== "info");
  return (
    <section className="section">
      <h2 className="section-title">
        Alerts
        <span className="aside">{snap ? warnings.length || "" : ""}</span>
      </h2>
      {warnings.length === 0 ? (
        <div className="all-clear">
          <span className={`dot ${snap ? "ok" : ""}`} />
          {snap ? "No alerts" : "Waiting for data"}
        </div>
      ) : (
        <ul className="alerts">
          {warnings.slice(0, MAX_ROWS).map((w) => (
            <li key={w.id}>
              <span className={`dot ${w.level}`} />
              <span>{w.msg}</span>
              <span className="sub">{w.subsystem}</span>
            </li>
          ))}
          {warnings.length > MAX_ROWS && (
            <li className="more" title={warnings.slice(MAX_ROWS).map((w) => w.msg).join("\n")}>
              + {warnings.length - MAX_ROWS} more
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
