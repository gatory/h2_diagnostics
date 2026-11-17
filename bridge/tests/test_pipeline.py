import asyncio
import json
import re
from pathlib import Path

from websockets.asyncio.client import connect

from h2_diagnostics import layout
from h2_diagnostics.sources.replay import ReplaySource
from h2_diagnostics.output import server
from h2_diagnostics.output.recorder import Recorder
from h2_diagnostics.processing.pipeline import H2Diagnostics

PKG = Path(__file__).resolve().parents[1] / "h2_diagnostics"


def test_snapshot_shape(recording):
    snap = H2Diagnostics(ReplaySource(recording)).tick(1.0)
    assert len(snap["body"]["joints"]) == layout.NUM_BODY == 31
    assert snap["body"]["spare_slots_active"] is False
    assert len(snap["battery"]["cells"]) == 18
    assert set(snap["imu"]) == {"pelvis", "torso"} and "imu" not in snap["body"]
    for where in ("pelvis", "torso"):
        assert len(snap["imu"][where]["quat"]) == 4
    for side in ("left", "right"):
        hand = snap["hands"][side]
        assert len(hand["motors"]) == 20
        assert sum(m["active"] for m in hand["motors"]) == 16
        assert len(hand["pressure"]) == 16 and len(hand["pressure"][0]) == 6
    json.dumps(snap, allow_nan=False)  # must be strict JSON for the browser


def test_record_then_replay_roundtrip(recording, tmp_path):
    rec = Recorder(tmp_path)
    bridge = H2Diagnostics(ReplaySource(recording), rec)
    path = rec.start("trial one", {"notes": "x"})
    for _ in range(60):
        bridge.tick(0.02)
        if _ == 30:
            rec.marker("halfway")
    rec.stop()
    assert path.name.endswith("_trial-one.jsonl")
    again = ReplaySource(path)
    assert again.meta["name"] == "trial one"
    assert [m["marker"] for m in again.markers] == ["halfway"]
    assert set(again.topics) <= set(ReplaySource(recording).topics)


def test_replay_loops(recording):
    src = ReplaySource(recording, loop=True)
    for _ in range(300):  # 6 s of virtual time over a 2.2 s file
        src.poll(0.02)
    assert not src.done
    assert src.stats["rt/lowstate"].count > 101


def test_server_streams_and_records(recording, tmp_path):
    async def scenario():
        bridge = H2Diagnostics(ReplaySource(recording, loop=True), Recorder(tmp_path))
        task = asyncio.create_task(server.run(bridge, "127.0.0.1", 8799, tick_hz=50, send_hz=25))
        await asyncio.sleep(0.3)
        try:
            async with connect("ws://127.0.0.1:8799") as ws:
                snap = json.loads(await ws.recv())
                assert snap["type"] == "snapshot" and snap["body"]
                await ws.send(json.dumps({"cmd": "record_start", "name": "ws test"}))
                await ws.send(json.dumps({"cmd": "marker", "text": "m1"}))
                await ws.send(json.dumps({"cmd": "record_stop"}))
                await ws.send("not json")
                acks = []
                while len(acks) < 4:
                    msg = json.loads(await ws.recv())
                    if msg["type"] == "ack":
                        acks.append(msg)
                assert [a["ok"] for a in acks] == [True, True, True, False]
        finally:
            task.cancel()
        return acks[0]["file"]

    name = asyncio.run(scenario())
    assert (tmp_path / name).exists()


def test_bridge_never_writes_to_robot():
    """Read-only guarantee until the Movement phase."""
    forbidden = re.compile(r"ChannelPublisher|CreateSendChannel|SetWriter|DataWriter|\bLowCmd_|HandCmd_|BmsCmd_")
    files = list(PKG.rglob("*.py"))  # rglob: every subfolder, not just the top level
    assert len(files) > 15, "guard found too few files; did the package move?"
    for py in files:
        assert not forbidden.search(py.read_text()), f"{py.relative_to(PKG)} references a DDS writer/command"
