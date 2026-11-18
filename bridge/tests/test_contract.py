"""The snapshot is a contract between the bridge and the dashboard.

dashboard/src/contract/snapshot.fixture.json is one real WebSocket message. The
dashboard type-checks it against its TypeScript types (`npm run typecheck`); this
test checks it still has the shape the bridge sends. Change either side alone and
one of the two fails.

After an intended snapshot change, regenerate the fixture, then update
dashboard/src/contract/snapshot.ts to match:

    UPDATE_FIXTURE=1 python -m pytest tests/test_contract.py
"""
import json
import os
from pathlib import Path

from h2_diagnostics.output.recorder import Recorder
from h2_diagnostics.processing.pipeline import H2Diagnostics
from h2_diagnostics.sources.replay import ReplaySource

FIXTURE = Path(__file__).resolve().parents[2] / "dashboard/src/contract/snapshot.fixture.json"
MAPS = {"topics"}  # dicts keyed by data (topic names), not by field names


def _hot_knee(rec):
    # One warm motor so the fixture carries a real warning (the at-rest recording
    # has none, and an empty list would leave the dashboard's Warning type untested).
    if rec["topic"] == "rt/lowstate":
        rec["data"]["motor_state"][9]["temperature"] = [72, 60]
    return rec


def wire_message(recording, tmp_path):
    """One snapshot exactly as server.run broadcasts it, with a recording active."""
    rec = Recorder(tmp_path / "sessions")
    bridge = H2Diagnostics(ReplaySource(recording), rec)
    rec.start("fixture", {})
    for _ in range(50):  # 1 s, so topic rates are filled in
        snap = bridge.tick(0.02)
    rec.stop()
    return {"type": "snapshot", **snap}


def shape(value, key=None):
    """Key names and nesting only: values vary, structure is the contract."""
    if isinstance(value, dict):
        if key in MAPS:
            return {"<any>": shape(next(iter(value.values()), None))}
        return {k: shape(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return "value"  # numbers, strings, bools and None are all leaves


def test_dashboard_fixture_matches_the_bridge(scenario, tmp_path):
    msg = wire_message(scenario("fixture", _hot_knee), tmp_path)
    assert msg["warnings"], "the fixture needs at least one warning"
    json.dumps(msg, allow_nan=False)
    if os.environ.get("UPDATE_FIXTURE"):
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(msg, indent=1) + "\n")
    fixture = json.loads(FIXTURE.read_text())
    assert shape(msg) == shape(fixture), (
        "The snapshot's shape changed. If intended: UPDATE_FIXTURE=1 python -m pytest "
        "tests/test_contract.py, then update dashboard/src/contract/snapshot.ts")
