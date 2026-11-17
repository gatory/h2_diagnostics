"""③ WebSocket server: streams snapshots to the dashboard app, takes recorder commands.

Server -> app:   {"type": "snapshot", ...snapshot}      at send_hz
                 {"type": "ack", "cmd": ..., ...}        after each command
App -> server:   {"cmd": "record_start", "name": "...", "notes": "..."}
                 {"cmd": "record_stop"}
                 {"cmd": "marker", "text": "..."}

Commands only control the recorder. Nothing here can reach the robot.
"""
import asyncio
import json
import logging
import time

from websockets.asyncio.server import broadcast, serve

from .. import layout

log = logging.getLogger("h2_diagnostics.server")


def _handle_command(bridge, msg):
    rec = bridge.recorder
    cmd = msg.get("cmd")
    if rec is None:
        return {"ok": False, "error": "recorder disabled"}
    if cmd == "record_start":
        meta = {
            "notes": msg.get("notes", ""),
            "source": "live" if bridge.source.live else "replay",
            "joint_names": layout.BODY_JOINTS,
            "joint_order_verified": layout.JOINT_ORDER_VERIFIED,
        }
        path = rec.start(msg.get("name", ""), meta)
        return {"ok": True, "file": path.name}
    if cmd == "record_stop":
        path = rec.stop()
        return {"ok": True, "file": path.name if path else None}
    if cmd == "marker":
        rec.marker(str(msg.get("text", "")))
        return {"ok": rec.active}
    return {"ok": False, "error": f"unknown cmd {cmd!r}"}


async def run(bridge, host="0.0.0.0", port=8765, tick_hz=50.0, send_hz=25.0):
    clients = set()

    async def handler(ws):
        clients.add(ws)
        log.info("client connected: %s", ws.remote_address)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    reply = _handle_command(bridge, msg)
                except Exception as e:  # bad JSON or recorder error: report, keep going
                    msg, reply = {}, {"ok": False, "error": repr(e)}
                await ws.send(json.dumps({"type": "ack", "cmd": msg.get("cmd"), **reply}))
        finally:
            clients.discard(ws)
            log.info("client left: %s", ws.remote_address)

    async with serve(handler, host, port, max_size=2**20):
        log.info("serving on ws://%s:%d (%s)", host, port,
                 "live" if bridge.source.live else "replay")
        period = 1.0 / tick_hz
        send_every = max(1, round(tick_hz / send_hz))
        last = time.monotonic()
        n = 0
        while not bridge.source.done:
            await asyncio.sleep(period)
            now = time.monotonic()
            snap = bridge.tick(now - last)
            last = now
            n += 1
            if n % send_every == 0 and clients:
                broadcast(clients, json.dumps({"type": "snapshot", **snap}))
        log.info("source finished")
