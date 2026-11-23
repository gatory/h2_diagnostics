/**
 * Mounts the three.js RobotScene once and hands it a way to read the newest snapshot.
 * React never re-renders the 3D: the scene pulls `bridge.latest` on its own frames.
 */
import { useEffect, useRef, useState } from "react";
import { useBridgeInstance } from "../bridge";
import { RobotScene } from "../robot/scene";

export function RobotView() {
  const bridge = useBridgeInstance();
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const scene = new RobotScene(el, () => bridge.latest);
    let alive = true;
    scene.start();
    scene
      .load()
      .then(() => alive && setLoading(false))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
      scene.dispose();
    };
  }, [bridge]);

  return (
    <div className="robot-view" ref={host}>
      {(loading || error) && <div className="hero-note">{error ? `3D model failed: ${error}` : "Loading model…"}</div>}
    </div>
  );
}
