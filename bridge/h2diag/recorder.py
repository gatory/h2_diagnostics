"""Session recorder. Writes the same .jsonl format stream_sensors.py uses, so
ReplaySource can play back old and new recordings alike:

    {"meta": {...}}                                  first line
    {"t": 1.234, "topic": "rt/lf/lowstate", "data": {...}}
    {"t": 5.678, "marker": "started gait trial 3"}

Records the newest message per topic at each bridge tick (50 Hz by default), so
the 100 Hz hand topics are stored at the tick rate.
"""
import gzip
import json
import re
import time
from datetime import datetime
from pathlib import Path

_STAMP = re.compile(r"(\d{8}_\d{6})")  # 20261112_150110 in a file name


def _slug(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")[:40]


class Recorder:
    def __init__(self, sessions_dir):
        self.dir = Path(sessions_dir)
        self._f = None
        self._t0 = None
        self.path = None
        self.name = None

    @property
    def active(self):
        return self._f is not None

    def start(self, name="", meta=None):
        if self.active:
            self.stop()
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.name = name
        self.path = self.dir / (f"{stamp}_{_slug(name)}.jsonl" if name else f"{stamp}.jsonl")
        self._f = open(self.path, "w")
        self._t0 = time.monotonic()
        header = {"start": datetime.now().isoformat(timespec="seconds"), "name": name}
        header.update(meta or {})
        self._f.write(json.dumps({"meta": header}) + "\n")
        return self.path

    def _t(self):
        return round(time.monotonic() - self._t0, 4)

    def write(self, topic, data):
        if self.active:
            self._f.write(json.dumps({"t": self._t(), "topic": topic, "data": data}) + "\n")

    def marker(self, text):
        if self.active:
            self._f.write(json.dumps({"t": self._t(), "marker": text}) + "\n")
            self._f.flush()

    def status(self):
        if not self.active:
            return {"recording": False}
        return {"recording": True, "name": self.name, "file": self.path.name,
                "elapsed_s": round(time.monotonic() - self._t0, 1)}

    def stop(self):
        path = self.path
        if self._f:
            self._f.close()
        self._f = None
        self.path = None
        return path


# ---------------------------------------------------------------- reading sessions

def recording_start(meta, path):
    """When a recording began: meta["start"] if present, else the file-name stamp."""
    try:
        return datetime.fromisoformat(meta["start"])
    except (KeyError, TypeError, ValueError):
        m = _STAMP.search(Path(path).name)
        return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S") if m else None


def _open(path):
    return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)


def _tail_t(path):
    """`t` of the last record, read from the end of the file so big files stay fast.
    None for .gz (can't seek backwards cheaply) or if nothing parses."""
    if str(path).endswith(".gz"):
        return None
    with open(path, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 256 * 1024))  # a lowstate line is ~10 KB
        lines = f.read().splitlines()
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:  # the first line may be cut in half by the seek
            continue
        if "t" in rec:
            return rec["t"]
    return None


def session_info(path):
    """Header facts about one recording without loading it."""
    path = Path(path)
    meta, first_t = {}, None
    with _open(path) as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if "meta" in rec:
                meta = rec["meta"]
                continue
            if "t" in rec:
                first_t = rec["t"]
                break
    last_t = _tail_t(path) if first_t is not None else None
    return {
        "path": path,
        "start": recording_start(meta, path),
        "name": meta.get("name") or "",
        "notes": meta.get("notes") or "",
        "empty": first_t is None,
        "duration_s": None if last_t is None else round(last_t - first_t, 1),
        "size_mb": round(path.stat().st_size / 1e6, 1),
    }


def list_sessions(dirs):
    """All recordings in `dirs`, newest first."""
    paths = {p for d in map(Path, dirs) if d.is_dir()
             for pattern in ("*.jsonl", "*.jsonl.gz") for p in d.glob(pattern)}
    infos = [session_info(p) for p in paths]
    return sorted(infos, key=lambda s: (s["start"] or datetime.min, s["path"].name), reverse=True)
