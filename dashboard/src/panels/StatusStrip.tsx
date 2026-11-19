/**
 * Top bar: connection, data source, battery, mode, main board, topic health.
 * Colours come only from the bridge's warnings (status.ts); `_raw` fields get a "?".
 */
import type { CSSProperties, ReactNode } from "react";
import type { ConnectionStatus } from "../bridge/BridgeClient";
import { useBridge } from "../bridge/useBridge";
import type { WarningLevel } from "../contract/snapshot";
import { COLORS, levelCss, UNCONFIRMED } from "../ui/theme";
import { clockText, maxReading, SECTION_IDS, topicDots, worstLevel } from "./status";

export const STRIP_HEIGHT = 40;

const CONNECTION: Record<ConnectionStatus, { text: string; color: string }> = {
  live: { text: "connected", color: COLORS.ok },
  stale: { text: "no data", color: COLORS.notice },
  connecting: { text: "connecting…", color: COLORS.dim },
  disconnected: { text: "disconnected", color: "#e5484d" },
};

export function StatusStrip() {
  const { status, latest: s } = useBridge();
  const conn = CONNECTION[status];
  const level = (match: (id: string) => boolean) => (s ? worstLevel(s.warnings, match) : null);

  return (
    <div style={STRIP}>
      <Item>
        <Dot color={conn.color} />
        {conn.text}
      </Item>
      {s && (
        <>
          <Item>
            <span style={{ ...BADGE, background: s.source === "live" ? "#b4232a" : "#2f5fb3" }}>
              {s.source.toUpperCase()}
            </span>
            {clockText(s) && <span style={{ color: COLORS.dim }}>{clockText(s)}</span>}
          </Item>
          <Item label="battery" level={level(SECTION_IDS.battery)}
                title={s.battery ? `current ${s.battery.current_raw}${UNCONFIRMED} (probably mA, negative = discharge; T4 confirms)` : undefined}>
            {s.battery
              ? `${s.battery.soc}% · ${s.battery.voltage.toFixed(1)} V · Δcell ${s.battery.cell_spread_mv ?? "–"} mV · ${maxReading(s.battery.temps) ?? "–"} °C`
              : "no data"}
          </Item>
          <Item label="mode">
            <span style={{ color: COLORS.dim }}>
              fsm {s.mode.fsm_name_raw ?? s.mode.fsm_id_raw ?? "–"}
              {UNCONFIRMED} · machine {s.body?.mode_machine ?? "–"}
              {UNCONFIRMED}
            </span>
          </Item>
          <Item label="board" level={level(SECTION_IDS.board)}>
            {s.mainboard ? `${maxReading(s.mainboard.temps) ?? "–"} °C` : "no data"}
          </Item>
          <Item label="topics" level={level(SECTION_IDS.comms)}>
            <span style={{ display: "flex", gap: 10 }}>
              {/* rates only on hover, or inline when that topic has a warning */}
              {topicDots(s).map((d) => (
                <span key={d.topic} title={`${d.topic}: ${d.text}`} style={{ whiteSpace: "nowrap", cursor: "default" }}>
                  <Dot color={levelCss(d.level)} />
                  {d.label}
                  {d.level && <span style={{ color: levelCss(d.level) }}> {d.text}</span>}
                </span>
              ))}
            </span>
          </Item>
        </>
      )}
    </div>
  );
}

function Item({ label, level, title, children }:
  { label?: string; level?: WarningLevel | null; title?: string; children: ReactNode }) {
  return (
    <div title={title} style={{ display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap" }}>
      {label && <span style={{ color: level ? levelCss(level) : COLORS.dim }}>{label}</span>}
      {children}
    </div>
  );
}

function Dot({ color }: { color: string }) {
  return <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 4, background: color, marginRight: 4 }} />;
}

const STRIP: CSSProperties = {
  position: "absolute", top: 0, left: 0, right: 0, height: STRIP_HEIGHT, boxSizing: "border-box",
  display: "flex", alignItems: "center", gap: 16, padding: "0 16px", overflow: "hidden",
  background: "rgba(10,13,16,0.92)", borderBottom: `1px solid ${COLORS.border}`,
  color: COLORS.text, font: "13px system-ui",
};
const BADGE: CSSProperties = { color: "white", fontWeight: 600, fontSize: 11, padding: "2px 6px", borderRadius: 4 };
