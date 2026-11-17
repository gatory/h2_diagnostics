"""④ Preflight report as plain text (the data comes from processing/preflight.py)."""


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
