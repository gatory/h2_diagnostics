/**
 * The bridge's warnings, worst first (the bridge already sorts them).
 * The dashboard never adds warnings of its own.
 */
import { useBridge } from "../bridge/useBridge";
import { COLORS, levelCss, PANEL } from "../ui/theme";

export function WarningsPanel() {
  const { latest } = useBridge();
  if (!latest) return null;
  const ws = latest.warnings;
  return (
    <div style={{ ...PANEL, position: "relative", maxHeight: "25vh", overflowY: "auto" }}>
      <div style={{ color: COLORS.dim, marginBottom: ws.length ? 6 : 0 }}>
        {ws.length ? `warnings (${ws.length})` : "no warnings"}
      </div>
      {ws.map((w) => (
        <div key={w.id} style={{ display: "flex", gap: 8, padding: "2px 0" }}>
          <span style={{ color: levelCss(w.level), width: 38, flexShrink: 0, fontSize: 11, fontWeight: 600 }}>
            {w.level.toUpperCase()}
          </span>
          <span>{w.msg}</span>
        </div>
      ))}
    </div>
  );
}
