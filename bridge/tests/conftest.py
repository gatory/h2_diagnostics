import copy
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from h2_diagnostics.sources import dds

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


# ------------------------------------------------------------------ fake DDS (no robot)

@dataclass
class FakeMsg:  # stands in for a decoded IDL message (those are dataclasses too)
    value: int


class FakeDDS:
    """Replaces the functions in sources/dds.py. Records what LiveSource asks for and
    lets the test deliver messages the way a DDS thread would (by calling the handler)."""

    def __init__(self):
        self.inited = None
        self.handlers = {}  # topic -> handler LiveSource registered
        self.types = {}  # topic -> type name it asked for
        self.closed = []

    def init(self, domain, iface):
        self.inited = (domain, iface)

    def hg_type(self, name):
        return name  # a real class isn't needed; just remember which one was asked for

    def lookup_type(self, full_name):
        return None if "Unknown" in full_name else full_name

    def subscribe(self, topic, msg_type, on_message):
        self.handlers[topic] = on_message
        self.types[topic] = msg_type
        fake = self

        class Sub:
            def close(self):
                fake.closed.append(topic)

        return Sub()

    def deliver(self, topic, value):
        self.handlers[topic](FakeMsg(value))


@pytest.fixture
def fake_dds(monkeypatch):
    fake = FakeDDS()
    for name in ("init", "hg_type", "lookup_type", "subscribe"):
        monkeypatch.setattr(dds, name, getattr(fake, name))
    return fake
