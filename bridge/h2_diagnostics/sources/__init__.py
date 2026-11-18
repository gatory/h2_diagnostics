"""1. SOURCES: getting messages from the robot (DDS) or from recordings on disk.

Nothing here interprets messages; that's processing/. Lower layer: must not
import processing/, output/ or views/ (tests/test_layers.py checks).

    base.py      Source          the interface (ABC) both sources implement
    live.py      LiveSource      reads the robot's DDS topics
    replay.py    ReplaySource    plays a .jsonl / .jsonl.gz recording on a virtual clock
    stats.py     TopicStats      per-topic arrival count, rate, age
    sessions.py                  list/inspect recordings on disk
    dds.py                       THE gateway to DDS: init, subscribe (read-only), type
                                 registry, discovery. Only file that imports the SDK.
    probe.py                     topic sampling + rate probe (through dds.py)
    convert.py                   to_dict / num helpers (JSON-safe values)

READ-ONLY: only DDS readers are ever created. tests/test_pipeline.py checks it.
"""
from .base import Source
from .live import LiveSource
from .replay import ReplaySource
from .stats import TopicStats

__all__ = ["Source", "LiveSource", "ReplaySource", "TopicStats"]
