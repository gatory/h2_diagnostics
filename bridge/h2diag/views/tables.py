"""④ Tables for the CLI: recordings, discovered topics, topic rates, end-of-run summary.

Each function returns something printable (a rich Table or a string) and prints
nothing itself, so the CLI decides where output goes and tests can check it.
"""
from rich import box
from rich.table import Table
from rich.text import Text


def sessions_table(sessions):
    """Recordings, newest first, numbered for `h2diag replay <#>`."""
    t = Table(box=box.SIMPLE_HEAD, pad_edge=False)
    for col, just in (("#", "right"), ("recorded", "left"), ("duration", "right"),
                      ("size", "right"), ("name / file", "left")):
        t.add_column(col, justify=just)
    for k, s in enumerate(sessions, 1):
        when = f"{s['start']:%a %Y-%m-%d %H:%M}" if s["start"] else "?"
        if s["empty"]:
            dur = Text("empty", "dim")
        else:
            dur = "?" if s["duration_s"] is None else f"{s['duration_s']} s"
        label = f"“{s['name']}”  {s['path'].name}" if s["name"] else s["path"].name
        t.add_row(str(k), when, dur, f"{s['size_mb']} MB", label)
    return t


def _hz_label(r):
    if r["hz"]:
        return f"{r['hz']:.1f}"
    return "0 (silent)" if r["decoded"] else "-"


def _decoded_label(r):
    return "yes" if r["decoded"] else ("err" if r["error"] else "unknown type")


def topics_table(results, title):
    """Discovered topics (data/probe.py summarize_discovery) as a rich table."""
    t = Table(title=title, box=box.SIMPLE_HEAD)
    t.add_column("topic", no_wrap=True)  # the one column that must stay readable
    t.add_column("type", overflow="fold")  # long ROS type names wrap instead
    t.add_column("Hz", justify="right", no_wrap=True)
    t.add_column("writers", justify="right")
    t.add_column("decoded", no_wrap=True)
    for r in results:
        dec = _decoded_label(r)
        style = "" if r["decoded"] else ("red" if r["error"] else "yellow")
        t.add_row(r["topic"], r["type"], _hz_label(r), str(r["writers"]), Text(dec, style))
    return t


def topics_text(results):
    """Same table as plain text, the topics.txt format discover_topics.py wrote."""
    lines = [f"{'topic':40} {'type':45} {'Hz':>9} {'writers':>7} decoded"]
    for r in results:
        dec = "yes" if r["decoded"] else ("err" if r["error"] else "unknown")
        lines.append(f"{r['topic']:40} {r['type']:45} {_hz_label(r):>9} {r['writers']:>7} {dec}")
    return "\n".join(lines) + "\n"


def rates_table(rows, total, title):
    """Rate probe result (data/probe.py summarize_rates)."""
    t = Table(title=title, box=box.SIMPLE_HEAD)
    for col in ("topic", "Hz", "mean gap ms", "max gap ms"):
        t.add_column(col, justify="left" if col == "topic" else "right")
    fmt = lambda x: "-" if x is None else f"{x:.2f}"
    for r in rows:
        t.add_row(r["topic"], f"{r['hz']:.1f}", fmt(r["mean_gap_ms"]), fmt(r["max_gap_ms"]))
    t.add_section()
    t.add_row(Text("total msg/s", "bold"), Text(f"{total:.1f}", "bold"), "", "")
    return t


def summary_table(stats, elapsed_s):
    """Per-topic message counts after a live/replay session (like stream_sensors.py's)."""
    t = Table(title=f"Summary ({elapsed_s:.1f} s)", box=box.SIMPLE_HEAD)
    for col in ("topic", "msgs", "avg Hz"):
        t.add_column(col, justify="left" if col == "topic" else "right")
    for name, st in stats.items():
        hz = 0.0
        if st.count > 1 and st.last > st.first:
            hz = (st.count - 1) / (st.last - st.first)
        t.add_row(name, str(st.count), f"{hz:.1f}")
    return t
