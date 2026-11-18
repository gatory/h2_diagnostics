import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fixture } from "../contract/fixture";
import { BridgeClient, type SocketLike } from "./BridgeClient";

/** A WebSocket stand-in the test drives by hand (like FakeDDS on the bridge side). */
class FakeSocket implements SocketLike {
  readyState = 0;
  onopen: SocketLike["onopen"] = null;
  onclose: SocketLike["onclose"] = null;
  onerror: SocketLike["onerror"] = null;
  onmessage: SocketLike["onmessage"] = null;
  sent: string[] = [];
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.readyState = 3;
    this.onclose?.({});
  }
  // test helpers
  open() {
    this.readyState = 1;
    this.onopen?.({});
  }
  receive(msg: unknown) {
    this.onmessage?.({ data: typeof msg === "string" ? msg : JSON.stringify(msg) });
  }
}

let sockets: FakeSocket[];
let clock: number;
const make = () =>
  new BridgeClient("ws://test", {
    makeSocket: () => {
      const s = new FakeSocket();
      sockets.push(s);
      return s;
    },
    now: () => clock,
    staleMs: 500,
    retryMinMs: 100,
    retryMaxMs: 400,
  });

beforeEach(() => {
  sockets = [];
  clock = 0;
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

describe("BridgeClient", () => {
  it("goes live on the first snapshot and keeps the newest", () => {
    const c = make().start();
    expect(c.getState().status).toBe("connecting");
    sockets[0].open();
    sockets[0].receive(fixture);
    sockets[0].receive({ ...fixture, t: fixture.t + 1 });
    expect(c.getState().status).toBe("live");
    expect(c.latest?.t).toBe(fixture.t + 1);
  });

  it("notifies subscribers and keeps state identity until a change", () => {
    const c = make().start();
    const seen = vi.fn();
    c.subscribe(seen);
    const before = c.getState();
    expect(c.getState()).toBe(before); // useSyncExternalStore relies on this
    sockets[0].open();
    sockets[0].receive(fixture);
    expect(seen).toHaveBeenCalled();
    expect(c.getState()).not.toBe(before);
  });

  it("marks the data stale when snapshots stop, live again when they resume", () => {
    const c = make().start();
    sockets[0].open();
    sockets[0].receive(fixture);
    clock = 600;
    vi.advanceTimersByTime(100);
    expect(c.getState().status).toBe("stale");
    expect(c.latest).not.toBeNull(); // last known values stay visible
    sockets[0].receive(fixture);
    expect(c.getState().status).toBe("live");
  });

  it("reconnects with growing backoff after a drop", () => {
    const c = make().start();
    sockets[0].close();
    expect(c.getState().status).toBe("disconnected");
    vi.advanceTimersByTime(100);
    expect(sockets).toHaveLength(2); // retried after 100 ms
    sockets[1].close();
    vi.advanceTimersByTime(100);
    expect(sockets).toHaveLength(2); // now waits 200 ms
    vi.advanceTimersByTime(100);
    expect(sockets).toHaveLength(3);
  });

  it("sends recorder commands only while connected, and stores the ack", () => {
    const c = make().start();
    expect(c.send({ cmd: "record_stop" })).toBe(false);
    sockets[0].open();
    expect(c.send({ cmd: "marker", text: "lift arm" })).toBe(true);
    expect(JSON.parse(sockets[0].sent[0])).toEqual({ cmd: "marker", text: "lift arm" });
    sockets[0].receive({ type: "ack", cmd: "marker", ok: true });
    expect(c.getState().lastAck?.ok).toBe(true);
  });

  it("ignores non-JSON and stops retrying after stop()", () => {
    const c = make().start();
    sockets[0].receive("not json");
    expect(c.latest).toBeNull();
    c.stop();
    vi.advanceTimersByTime(1000);
    expect(sockets).toHaveLength(1);
    expect(c.getState().status).toBe("disconnected");
  });
});
