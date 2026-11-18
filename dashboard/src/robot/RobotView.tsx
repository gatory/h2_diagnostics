/**
 * The 3D robot panel: a React wrapper around RobotScene.
 * React only creates/disposes the scene and draws the text overlay; the scene
 * pulls snapshots from the BridgeClient on its own animation loop.
 */
import { useEffect, useRef, useState } from "react";
import { useBridge, useBridgeClient } from "../bridge/useBridge";
import { poseFromSnapshot } from "./pose";
import { RobotScene } from "./RobotScene";

type LoadState = { kind: "loading" } | { kind: "ready" } | { kind: "error"; message: string };

export function RobotView() {
  const client = useBridgeClient();
  const mount = useRef<HTMLDivElement>(null);
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    const scene = new RobotScene(mount.current!, () => client.latest).start();
    let alive = true; // StrictMode mounts twice in dev: ignore the first scene's promise
    scene.load().then(
      () => alive && setLoad({ kind: "ready" }),
      (e: Error) => alive && setLoad({ kind: "error", message: e.message }),
    );
    return () => {
      alive = false;
      scene.dispose();
    };
  }, [client]);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div ref={mount} style={{ position: "absolute", inset: 0 }} />
      <Overlay load={load} />
    </div>
  );
}

/** Small re-rendering part: load state and "why the pose isn't trustworthy". */
function Overlay({ load }: { load: LoadState }) {
  const { latest } = useBridge();
  const frozen = latest ? poseFromSnapshot(latest).frozen : "waiting for the bridge";
  const lines = [
    load.kind === "loading" && "loading robot model…",
    load.kind === "error" && `model failed: ${load.message}`,
    frozen && `pose not shown: ${frozen}`,
  ].filter(Boolean);
  if (!lines.length) return null;
  return (
    <div style={{ position: "absolute", bottom: 16, left: "50%", transform: "translateX(-50%)",
                  color: "#f0c060", font: "13px system-ui", textAlign: "center", pointerEvents: "none" }}>
      {lines.map((l) => <div key={String(l)}>{l}</div>)}
    </div>
  );
}
