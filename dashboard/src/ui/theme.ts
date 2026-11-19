/** Shared look: colours and panel styles used by every panel. */
import type { CSSProperties } from "react";
import type { WarningLevel } from "../contract/snapshot";

export const COLORS = {
  bg: 0x101418,
  text: "#cfd6dd",
  dim: "#8a96a3",
  border: "#2a323b",
  panel: "rgba(16,20,24,0.85)",
  ok: "#46a758",
  notice: "#f0c060",
};

/** Warning levels: the only place their colours are defined. */
export const LEVEL_COLOR: Record<WarningLevel, number> = { error: 0xe5484d, warn: 0xf5a524, info: 0x5b8def };

export const hex = (c: number) => "#" + c.toString(16).padStart(6, "0");
export const levelCss = (level: WarningLevel | null) => (level ? hex(LEVEL_COLOR[level]) : COLORS.ok);

export const PANEL: CSSProperties = {
  position: "absolute",
  color: COLORS.text,
  font: "13px system-ui",
  background: COLORS.panel,
  border: `1px solid ${COLORS.border}`,
  borderRadius: 8,
  padding: "10px 12px",
  boxSizing: "border-box",
};

/** "?" marker for fields whose meaning is unconfirmed (`_raw`): shown, never coloured. */
export const UNCONFIRMED = " ?";
