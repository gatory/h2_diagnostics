import copy
import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent / "data"
RECORDING = DATA / "sensors_20261112_150110.jsonl"  # real robot, 2026-11-12, at rest
TOPICS = DATA / "topics_20261113.json"  # real discovery output, 120 topics


def load_recording():
    lines = [json.loads(l) for l in RECORDING.read_text().splitlines() if l.strip()]
    return lines[0], lines[1:]


@pytest.fixture
def recording():
    return RECORDING


@pytest.fixture
def scenario(tmp_path):
    """make(name, mutate) -> path of a copy of the real recording with `mutate`
    applied to every record (mutate may return None to drop the record)."""

    def make(name, mutate):
        meta, records = load_recording()
        out = tmp_path / f"{name}.jsonl"
        with out.open("w") as f:
            f.write(json.dumps(meta) + "\n")
            for rec in records:
                rec = mutate(copy.deepcopy(rec))
                if rec is not None:
                    f.write(json.dumps(rec) + "\n")
        return out

    return make
