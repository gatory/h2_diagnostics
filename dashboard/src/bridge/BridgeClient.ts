/**
 * BridgeClient: the dashboard's one door to the bridge (like dds.py on the bridge side).
 * Nothing else opens a WebSocket.
 *
 * Plain TypeScript, no React: it keeps the newest snapshot and a connection status,
 * and tells subscribers when either changes. React components read it through
 * useBridge() (useSyncExternalStore); the 3D view reads `latest` every frame instead,
 * so 25 snapshots/s don't re-render React.
 *
 * Status:  connecting -> live <-> stale  (stale = no snapshot for STALE_MS)
 *          any -> disconnected -> (backoff) -> connecting
 */
import type { Ack, Command, ServerMessage, Snapshot } from "../contract/snapshot";

export type ConnectionStatus = "connecting" | "live" | "stale" | "disconnected";

export interface BridgeState {
  status: ConnectionStatus;
  latest: Snapshot | null; // newest snapshot (kept while stale/disconnected)
  lastAck: Ack | null;
}

/** The parts of the browser WebSocket we use; tests pass a fake. */
export interface SocketLike {
  readyState: number;
  onopen: ((ev: unknown) => void) | null;
  onclose: ((ev: unknown) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  send(data: string): void;
  close(): void;
}

export interface BridgeOptions {
  makeSocket?: (url: string) => SocketLike;
  staleMs?: number;
  retryMinMs?: number;
  retryMaxMs?: number;
  now?: () => number;
}

const OPEN = 1; // WebSocket.OPEN

export class BridgeClient {
  readonly url: string;
  private readonly makeSocket: (url: string) => SocketLike;
  private readonly staleMs: number;
  private readonly retryMinMs: number;
  private readonly retryMaxMs: number;
  private readonly now: () => number;

  private state: BridgeState = { status: "disconnected", latest: null, lastAck: null };
  private readonly listeners = new Set<() => void>();
  private socket: SocketLike | null = null;
  private retryMs: number;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private staleTimer: ReturnType<typeof setInterval> | null = null;
  private lastSnapshotAt = 0;
  private stopped = true;

  constructor(url: string, opts: BridgeOptions = {}) {
    this.url = url;
    this.makeSocket = opts.makeSocket ?? ((u) => new WebSocket(u) as unknown as SocketLike);
    this.staleMs = opts.staleMs ?? 500;
    this.retryMinMs = opts.retryMinMs ?? 500;
    this.retryMaxMs = opts.retryMaxMs ?? 5000;
    this.now = opts.now ?? (() => performance.now());
    this.retryMs = this.retryMinMs;
  }

  // ---- lifecycle ----------------------------------------------------------------

  start(): this {
    if (!this.stopped) return this;
    this.stopped = false;
    this.connect();
    this.staleTimer = setInterval(() => this.checkStale(), 100);
    return this;
  }

  stop(): void {
    this.stopped = true;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    if (this.staleTimer) clearInterval(this.staleTimer);
    this.retryTimer = this.staleTimer = null;
    const s = this.socket;
    this.socket = null;
    s?.close();
    this.set({ status: "disconnected" });
  }

  // ---- reading (React: useSyncExternalStore(subscribe, getState)) -------------------

  /** Returns the same object until something changes (useSyncExternalStore needs that). */
  getState = (): BridgeState => this.state;

  get latest(): Snapshot | null {
    return this.state.latest;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  // ---- commands (recorder only) ------------------------------------------------------

  /** False if not connected; the reply arrives later as `lastAck`. */
  send(command: Command): boolean {
    if (!this.socket || this.socket.readyState !== OPEN) return false;
    this.socket.send(JSON.stringify(command));
    return true;
  }

  // ---- internals ------------------------------------------------------------------

  private connect(): void {
    this.set({ status: "connecting" });
    const s = this.makeSocket(this.url);
    this.socket = s;
    s.onopen = () => {
      this.retryMs = this.retryMinMs; // healthy again: next drop retries fast
    };
    s.onmessage = (ev) => this.onMessage(ev.data);
    s.onerror = () => s.close(); // onclose does the retry
    s.onclose = () => {
      if (this.socket !== s) return; // an old socket we already replaced or stopped
      this.socket = null;
      this.set({ status: "disconnected" });
      if (!this.stopped) this.scheduleRetry();
    };
  }

  private scheduleRetry(): void {
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      if (!this.stopped) this.connect();
    }, this.retryMs);
    this.retryMs = Math.min(this.retryMs * 2, this.retryMaxMs);
  }

  private onMessage(data: unknown): void {
    let msg: ServerMessage;
    try {
      msg = JSON.parse(String(data)) as ServerMessage;
    } catch {
      return; // the bridge only sends JSON; ignore anything else
    }
    if (msg.type === "snapshot") {
      this.lastSnapshotAt = this.now();
      this.set({ status: "live", latest: msg });
    } else if (msg.type === "ack") {
      this.set({ lastAck: msg });
    }
  }

  private checkStale(): void {
    if (this.state.status === "live" && this.now() - this.lastSnapshotAt > this.staleMs) {
      this.set({ status: "stale" });
    }
  }

  private set(patch: Partial<BridgeState>): void {
    this.state = { ...this.state, ...patch };
    for (const l of this.listeners) l();
  }
}
