/**
 * The dashboard, laid out for a portrait monitor, top to bottom:
 *   top bar · robot (3D + status + readouts) · alerts · hands · topics · recorder dock
 *
 * Bridge address: ?bridge=ws://172.16.68.113:8765 for the Thor; default
 * ws://localhost:8765 (e.g. `python -m h2_diagnostics serve --replay <file>`).
 */
import { useEffect, useState } from "react";
import { Bridge, BridgeContext } from "./bridge";
import { Alerts } from "./components/Alerts";
import { HandCard } from "./components/HandCard";
import { Hero } from "./components/Hero";
import { RecorderDock } from "./components/RecorderDock";
import { Topics } from "./components/Topics";
import { TopBar } from "./components/TopBar";

const DEFAULT_BRIDGE = "ws://localhost:8765";

export function App() {
  const [bridge] = useState(() => new Bridge(new URLSearchParams(location.search).get("bridge") ?? DEFAULT_BRIDGE));
  useEffect(() => {
    bridge.start();
    return () => bridge.stop();
  }, [bridge]);

  return (
    <BridgeContext.Provider value={bridge}>
      <div className="app">
        <TopBar />
        <Hero />
        <Alerts />
        <section className="section hands">
          <HandCard side="left" />
          <HandCard side="right" />
        </section>
        <Topics />
        <RecorderDock />
      </div>
    </BridgeContext.Provider>
  );
}
