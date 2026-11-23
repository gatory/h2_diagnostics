/** One line of topic health: name + receive rate, amber/red from stale:/rate: warnings. */
import { useBridge } from "../bridge";
import { topicLabel, topicLevel } from "../derive";

export function Topics() {
  const { snap } = useBridge();
  if (!snap) return <div className="topics">Topics · waiting for the bridge</div>;
  const rows = Object.entries(snap.topics).sort(([a], [b]) => topicLabel(a).localeCompare(topicLabel(b)));
  return (
    <div className="topics">
      {rows.map(([topic, t]) => {
        const level = topicLevel(snap.warnings, topic);
        return (
          <span key={topic} className={`topic ${level ?? ""}`} title={topic}>
            <span className={`dot ${level ?? (t.count ? "ok" : "")}`} />
            {topicLabel(topic)}
            <span className="hz">{t.hz === null ? "…" : `${t.hz.toFixed(0)} Hz`}</span>
          </span>
        );
      })}
    </div>
  );
}
