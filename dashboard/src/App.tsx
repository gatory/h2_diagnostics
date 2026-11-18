/**
 * The dashboard shell. For now: one BridgeClient and a connection check.
 * Panels (3D robot, status strip, hands, warnings) plug in here next.
 *
 * Bridge address: ?bridge=ws://172.16.68.113:8765 (Thor), default ws://localhost:8765
 * (a replay bridge on this machine: `h2diag serve --replay <file>`).
 */
import { useEffect, useState } from "react";
import { BridgeClient } from "./bridge/BridgeClient";
import { BridgeContext, useBridge } from "./bridge/useBridge";

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
      <ConnectionCheck />
    </BridgeContext.Provider>
  );
}

/** Temporary: proves data arrives. Replaced by the status strip in step 5. */
function ConnectionCheck() {
  const { status, latest } = useBridge();
  return (
    <pre style={{ font: "14px monospace", padding: 16 }}>
      {`status   ${status}
source   ${latest?.source ?? "-"}
joints   ${latest?.body?.joints.length ?? "-"}
battery  ${latest?.battery ? `${latest.battery.soc}%  ${latest.battery.voltage} V` : "-"}
warnings ${latest ? latest.warnings.map((w) => `${w.level}: ${w.msg}`).join("; ") || "none" : "-"}`}
    </pre>
  );
}
