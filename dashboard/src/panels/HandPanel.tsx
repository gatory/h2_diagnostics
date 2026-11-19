/**
 * One Dex5 hand, in a lower corner: motor temperatures per finger (with raw q),
 * and the 16 pressure pads. Raw/unconfirmed values are labelled with "?".
 */
import type { CSSProperties } from "react";
import { useBridge } from "../bridge/useBridge";
import { heatColor, jointTemp } from "../robot/heat";
import { COLORS, hex, levelCss, PANEL, UNCONFIRMED } from "../ui/theme";
import { FINGERS, handLevel, handOf, motorLevels, padTiles, type Side } from "./hands";

export const HAND_PANEL_WIDTH = 330;
/** About how tall a panel with data is; other overlays keep clear of it. */
export const HAND_PANEL_HEIGHT = 280;

export function HandPanel({ side }: { side: Side }) {
  const { latest } = useBridge();
  const hand = handOf(latest, side);
  const warnings = latest?.warnings ?? [];
  const level = handLevel(warnings, side);
  const levels = motorLevels(warnings, side);
  const place: CSSProperties = side === "left" ? { left: 16 } : { right: 16 };

  return (
    <div style={{ ...PANEL, ...place, bottom: 16, width: HAND_PANEL_WIDTH }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ color: level ? levelCss(level) : COLORS.text, fontWeight: 600 }}>{side} hand</span>
        {hand && (
          <span style={{ color: COLORS.dim, fontSize: 11 }} title="hand supply (unconfirmed)">
            {hand.power_v_raw.toFixed(1)} V{UNCONFIRMED} · {hand.power_a_raw.toFixed(2)} A{UNCONFIRMED}
          </span>
        )}
      </div>
      {!hand ? (
        <div style={{ color: COLORS.dim }}>no data</div>
      ) : (
        <>
          <table style={{ borderSpacing: 3, margin: "-3px", font: "11px monospace" }}>
            <tbody>
              {FINGERS.map((f) => (
                <tr key={f.name}>
                  <td style={{ color: COLORS.dim, paddingRight: 4, font: "11px system-ui" }}>{f.name}</td>
                  {f.slots.map((slot) => {
                    const m = hand.motors[slot];
                    const t = m.active ? jointTemp(m.temp) : null;
                    const lvl = levels.get(slot);
                    return (
                      <td key={slot} title={`slot ${slot}: ${m.active ? `${m.temp.join("/")} °C, ` : "no temperature (thumb), "}q ${m.q}${UNCONFIRMED}, status ${m.motorstate}`}
                          style={{ ...CELL, background: m.active ? hex(heatColor(t, lvl)) : "#2a323b",
                                   color: m.active ? "#111" : COLORS.dim }}>
                        <div style={{ fontWeight: 600 }}>{m.active ? (t === null ? "–" : `${t}°`) : "q"}</div>
                        <div style={{ opacity: 0.75 }}>{m.q === null ? "inv" : m.q.toFixed(2)}</div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ color: COLORS.dim, fontSize: 11, margin: "8px 0 4px" }}>
            pressure pads (raw, uncalibrated{UNCONFIRMED})
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(8, 1fr)", gap: 3 }}>
            {padTiles(hand).map((p) => (
              <div key={p.pad} title={`pad ${p.pad}: peak |raw| ${p.peak}${p.lost ? " (lost)" : ""}`}
                   style={{ height: 18, borderRadius: 3, fontSize: 9, textAlign: "center", lineHeight: "18px",
                            color: p.fill > 0.5 ? "#111" : COLORS.dim,
                            background: p.lost
                              ? "repeating-linear-gradient(45deg,#3a2a2a,#3a2a2a 3px,#2a323b 3px,#2a323b 6px)"
                              : `rgba(91,141,239,${0.12 + 0.88 * p.fill})` }}>
                {p.lost ? "lost" : p.pad}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

const CELL: CSSProperties = { width: 52, padding: "2px 4px", borderRadius: 4, textAlign: "center", lineHeight: 1.25 };
