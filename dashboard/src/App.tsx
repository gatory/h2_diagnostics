/**
 * The dashboard shell: one BridgeClient (in a React context) and the panels.
 * The 3D robot fills the window; the other panels float over it.
 *
 * Bridge address: ?bridge=ws://172.16.68.113:8765 (Thor), default ws://localhost:8765
 * (a replay bridge on this machine: `h2diag serve --replay <file>`).
 */
import { useEffect, useState, type CSSProperties } from "react";
import { BridgeClient } from "./bridge/BridgeClient";
import { BridgeContext } from "./bridge/useBridge";
import { HandPanel } from "./panels/HandPanel";
import { RecorderPanel } from "./panels/RecorderPanel";
import { STRIP_HEIGHT, StatusStrip } from "./panels/StatusStrip";
import { WarningsPanel } from "./panels/WarningsPanel";
import { RobotView } from "./robot/RobotView";
import { PANEL } from "./ui/theme";

const DEFAULT_BRIDGE = "ws://localhost:8765";

export function App() {
  const [client] = useState(
    () => new BridgeClient(new URLSearchParams(location.search).get("bridge") ?? DEFAULT_BRIDGE),
  );
  useEffect(() => {
    client.start();
    return () => client.stop();
  }, [client]);

  return (
    <BridgeContext.Provider value={client}>
      <RobotView />
      <StatusStrip />
      <div style={LEFT_COLUMN}>
        <div style={{ ...PANEL, position: "relative" }}>
          <RecorderPanel />
        </div>
        <WarningsPanel />
      </div>
      <HandPanel side="left" />
      <HandPanel side="right" />
    </BridgeContext.Provider>
  );
}

/** Recorder + warnings stack under the strip, left side (hands own the lower corners). */
const LEFT_COLUMN: CSSProperties = {
  position: "absolute", top: STRIP_HEIGHT + 12, left: 16, width: 320,
  display: "flex", flexDirection: "column", gap: 8,
};
