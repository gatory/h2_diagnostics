"""The terminal viewer (`h2diag live` / `h2diag replay`) and the session list.

view.render is pure, so screens are rendered into a fake 150-column console and
checked as text: no terminal, no robot.
"""
import copy
import gzip
import io
import shutil

import pytest
from rich.console import Console

from h2_diagnostics import layout
from h2_diagnostics.__main__ import main
from h2_diagnostics.sources.replay import ReplaySource
from h2_diagnostics.sources.sessions import list_sessions
from h2_diagnostics.processing.pipeline import H2Diagnostics
from h2_diagnostics.views import sensors as view


def screen(snap, base, info, width=150):
    c = Console(file=io.StringIO(), width=width, record=True)
    c.print(view.render(snap, base, info))
    return c.export_text()


@pytest.fixture
def replay(recording):
    src = ReplaySource(recording, loop=True)
    snap = H2Diagnostics(src).tick(1.0)
    return src, snap


def test_replay_screen_says_replay_and_when_it_was_recorded(replay):
    src, snap = replay
    text = screen(snap, view.baseline_of(snap), view.describe(src, 1.0))
    assert "REPLAY" in text and "LIVE" not in text
    assert "recorded Thu 2026-11-12 15:01:10" in text
    assert "now showing 15:01:11.0" in text  # recorded wall time at the playback point


def test_live_screen_says_live(replay):
    _, snap = replay
    text = screen(snap, {}, {"mode": "live", "iface": "eth10", "up_s": 5})
    assert "● LIVE" in text and "REPLAY" not in text and "eth10" in text


def test_screen_fits_a_maximized_terminal_without_cutting(replay):
    src, snap = replay
    lines = screen(snap, view.baseline_of(snap), view.describe(src, 1.0)).splitlines()
    assert len(lines) <= 44
    assert not any("…" in l for l in lines)  # rich marks cut-off cells with …
    for name in layout.BODY_JOINTS:
        assert any(name in l for l in lines)  # full names, not truncated


def test_moved_joint_shows_delta_in_degrees(replay):
    src, snap = replay
    base = view.baseline_of(snap)
    moved = copy.deepcopy(snap)
    moved["body"]["joints"][18]["q"] += 0.3  # L_elbow bent by hand: 17.2°
    line = next(l for l in screen(moved, base, view.describe(src, 1.0)).splitlines() if "L_elbow" in l)
    assert "+17.2" in line


def test_ab_mode_marks_linkage_joints(replay):
    src, snap = replay
    snap = copy.deepcopy(snap)
    snap["body"]["mode_pr"] = 1
    text = screen(snap, {}, view.describe(src, 1.0))
    assert "L_ankle_pitch *" in text and "L_knee *" not in text


def test_screen_before_any_data():
    empty = {"source": "live", "topics": {}, "warnings": [], "hands": {}}
    text = screen(empty, {}, {"mode": "live", "iface": "eth10", "up_s": 0})
    assert "body: waiting for data" in text


def test_replay_reads_gzip(recording, tmp_path):
    gz = tmp_path / "rec.jsonl.gz"
    with open(recording, "rb") as src, gzip.open(gz, "wb") as dst:
        shutil.copyfileobj(src, dst)
    assert len(ReplaySource(gz).records) == len(ReplaySource(recording).records)


def test_position_and_loops(recording):
    src = ReplaySource(recording, loop=True)
    src.poll(1.0)
    assert src.position == pytest.approx(1.0) and src.loops == 0
    src.poll(src.duration)  # runs past the end: wraps around
    assert src.loops == 1 and src.position < src.duration


def test_list_sessions_newest_first(recording, tmp_path):
    shutil.copy(recording, tmp_path / "20261112_150110_t1_joints.jsonl")
    (tmp_path / "20261113_090000_empty.jsonl").write_text('{"meta": {"start": "2026-11-13T09:00:00"}}\n')
    sessions = list_sessions([tmp_path, tmp_path / "missing"])
    assert [s["path"].name for s in sessions] == [
        "20261113_090000_empty.jsonl", "20261112_150110_t1_joints.jsonl"]
    assert sessions[0]["empty"] and sessions[1]["duration_s"] == pytest.approx(2.2, abs=0.1)


def test_replay_command_lists_and_rejects_bad_numbers(recording, tmp_path, capsys):
    shutil.copy(recording, tmp_path / recording.name)
    assert main(["replay", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Thu 2026-11-12 15:01" in out and recording.name in out
    assert main(["replay", "7", "--dir", str(tmp_path)]) == 1
    assert "no recording #7" in capsys.readouterr().out


def test_live_banner_shows_recording_and_no_data_hint(replay):
    _, snap = replay
    info = {"mode": "live", "iface": "eth10", "up_s": 5, "no_data": True,
            "rec": {"recording": True, "file": "20261117_t1.jsonl", "elapsed_s": 12.0}}
    text = screen(snap, {}, info)
    assert "⏺ REC" in text and "20261117_t1.jsonl" in text
    assert "waiting for data" in text and "ip -br addr" in text


def test_run_records_while_viewing(recording, tmp_path):
    # The old stream_sensors.py --log: view and record at once. Replays the 2.2 s
    # sample at 4x without looping, into a fake console.
    from h2_diagnostics.output.recorder import Recorder

    rec = Recorder(tmp_path)
    path = rec.start("view test")
    out = io.StringIO()
    view.run(ReplaySource(recording, speed=4.0, loop=False), rec, Console(file=out, width=150))
    assert not rec.active  # run() closed it
    again = ReplaySource(path)
    assert len(again.records) > 50 and "rt/lowstate" in again.topics
    printed = out.getvalue()
    assert "Summary" in printed and "recording saved to" in printed
