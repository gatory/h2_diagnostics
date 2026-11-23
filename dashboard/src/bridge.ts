/**
 * Bridge: the dashboard's only connection to the robot side (one WebSocket to the
 * bridge). Plain TypeScript; React reads it through useBridge() below.
 *
 *   connecting -> live <-> stale (no snapshot for STALE_MS) -> ... -> offline -> retry
 *
 * The 3D view reads `bridge.latest` on its own animation frame instead of through
 * React, so 25 snapshots/s never re-render the scene.
 */
import { createContext, useContext, useSyncExternalStore } from "react";
import type { Ack, Command, Snapshot } from "./types";

export type Conn = "connecting" | "live" | "stale" | "offline";

export interface BridgeState {
  conn: Conn;
  snap: Snapshot | null; // newest snapshot (kept while stale/offline)
  ack: Ack | null; // newest reply to a command
}

const STALE_MS = 1000;
const RETRY_MIN_MS = 500;
const RETRY_MAX_MS = 5000;

export class Bridge {
  readonly url: string;
  private state: BridgeState = { conn: "offline", snap: null, ack: null };
  private readonly listeners = new Set<() => void>();
  private socket: WebSocket | null = null;
  private retryMs = RETRY_MIN_MS;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private staleTimer: ReturnType<typeof setInterval> | undefined;
  private lastSnapAt = 0;
  private running = false;

  constructor(url: string) {
    this.url = url;
  }

  get latest(): Snapshot | null {
    return this.state.snap;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.connect();
    this.staleTimer = setInterval(() => {
      if (this.state.conn === "live" && performance.now() - this.lastSnapAt > STALE_MS) this.set({ conn: "stale" });
    }, 200);
  }

  stop(): void {
    this.running = false;
    clearTimeout(this.retryTimer);
    clearInterval(this.staleTimer);
    const s = this.socket;
    this.socket = null;
    s?.close();
    this.set({ conn: "offline" });
  }

  /** Recorder commands only. False when not connected (nothing was sent). */
  send(command: Command): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(command));
    return true;
  }

  // For useSyncExternalStore: getState must return the same object until something changes.
  getState = (): BridgeState => this.state;
  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  private connect(): void {
    this.set({ conn: "connecting" });
    const s = new WebSocket(this.url);
    this.socket = s;
    s.onopen = () => (this.retryMs = RETRY_MIN_MS);
    s.onmessage = (ev) => this.onMessage(ev.data);
    s.onerror = () => s.close(); // onclose schedules the retry
    s.onclose = () => {
      if (this.socket !== s) return; // an old socket (stopped or replaced)
      this.socket = null;
      this.set({ conn: "offline" });
      if (!this.running) return;
      this.retryTimer = setTimeout(() => this.running && this.connect(), this.retryMs);
      this.retryMs = Math.min(this.retryMs * 2, RETRY_MAX_MS);
    };
  }

  private onMessage(data: unknown): void {
    let msg: Snapshot | Ack;
    try {
      msg = JSON.parse(String(data));
    } catch {
      return; // the bridge only sends JSON
    }
    if (msg.type === "snapshot") {
      this.lastSnapAt = performance.now();
      this.set({ conn: "live", snap: msg });
    } else if (msg.type === "ack") {
      this.set({ ack: msg });
    }
  }

  private set(patch: Partial<BridgeState>): void {
    this.state = { ...this.state, ...patch };
    for (const fn of this.listeners) fn();
  }
}

// ---- React access -----------------------------------------------------------------

export const BridgeContext = createContext<Bridge | null>(null);

export function useBridgeInstance(): Bridge {
  const b = useContext(BridgeContext);
  if (!b) throw new Error("useBridge outside <BridgeContext.Provider>");
  return b;
}

/** Re-renders on every change (~25/s): fine for text and small panels. */
export function useBridge(): BridgeState {
  const b = useBridgeInstance();
  return useSyncExternalStore(b.subscribe, b.getState);
}
