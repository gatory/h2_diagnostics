"""Preflight: watch the robot (or a recording) for a few seconds, report pass/warn/fail."""
import time

from .core import Bridge

WARMUP_S = 1.0  # ignore the first second while subscriptions connect
LEVELS = {"info": 0, "warn": 1, "error": 2}


def run(source, seconds=10.0, hz=50.0, realtime=True):
    """Returns a report dict. realtime=False runs a replay as fast as possible."""
    bridge = Bridge(source)
    dt = 1.0 / hz
    seen = {}  # warning id -> {"level", "msg", "ticks"}
    ticks = 0
    snap = None
    start = source.now()
    while source.now() - start < seconds and not source.done:
        if realtime:
            time.sleep(dt)
        snap = bridge.tick(dt)
        if source.now() - start < WARMUP_S:
            continue
        ticks += 1
        for w in snap["warnings"]:
            prev = seen.get(w["id"])
            if prev is None or LEVELS[w["level"]] > LEVELS[prev["level"]]:
                seen[w["id"]] = {**w, "ticks": (prev or {}).get("ticks", 0)}
            seen[w["id"]]["ticks"] += 1
    return _report(snap, seen, ticks, source.now() - start)


def _report(snap, seen, ticks, elapsed):
    worst = max((LEVELS[w["level"]] for w in seen.values()), default=0)
    verdict = {0: "PASS", 1: "WARN", 2: "FAIL"}[worst]
    if snap is None or ticks == 0:
        verdict = "FAIL"
    summary = {}
    if snap:
        body = snap.get("body")
        if body:
            hot = max(body["joints"], key=lambda j: max(j["temp"]))
            summary["hottest_joint"] = f"{hot['name']} {max(hot['temp'])} °C"
        for side, hand in (snap.get("hands") or {}).items():
            if hand:
                temps = [max(m["temp"]) for m in hand["motors"] if m["active"]]
                summary[f"hand_{side}_max_temp"] = f"{max(temps)} °C"
        b = snap.get("battery")
        if b:
            summary["battery"] = f"{b['soc']}%  {b['voltage']} V  spread {b['cell_spread_mv']} mV"
        summary["topics"] = {
            t: "no data" if s["hz"] is None else f"{s['hz']} Hz" for t, s in snap["topics"].items()
        }
    return {
        "verdict": verdict,
        "elapsed_s": round(elapsed, 1),
        "ticks": ticks,
        "findings": sorted(seen.values(), key=lambda w: -LEVELS[w["level"]]),
        "summary": summary,
    }


def format_report(rep):
    lines = [f"PREFLIGHT: {rep['verdict']}   ({rep['elapsed_s']} s observed)", ""]
    s = rep["summary"]
    for key in ("hottest_joint", "hand_left_max_temp", "hand_right_max_temp", "battery"):
        if key in s:
            lines.append(f"  {key:20} {s[key]}")
    for topic, hz in s.get("topics", {}).items():
        lines.append(f"  {topic:20} {hz}")
    lines.append("")
    if not rep["findings"]:
        lines.append("  no findings")
    for w in rep["findings"]:
        pct = 100 * w["ticks"] / max(rep["ticks"], 1)
        lines.append(f"  [{w['level'].upper():5}] {w['msg']}   ({pct:.0f}% of the time)")
    return "\n".join(lines)
