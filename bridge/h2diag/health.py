"""Rule-based health checks on a snapshot.

Only fields marked ✅/🟡 in docs/field_map.md feed rules. All thresholds are
PROVISIONAL guesses until we have baselines from real sessions (PLAN phase 4).
"""
import math

from . import layout

LIMITS = {
    "stale_s": 0.5,  # no message for this long -> error
    "rate_frac": 0.7,  # live rate below 70% of expected -> warn
    "body_temp": (70, 85),  # (warn, error) °C, max of the two sensors
    "hand_temp": (75, 85),  # hands sit at 42-66 °C at rest
    "board_temp": (75, 85),
    "battery_temp": (50, 60),
    "soc": (20, 10),  # warn at or below, error at or below
    "cell_spread_mv": (50, 100),
    "motor_vol_frac": 0.85,  # motor supply below 85% of pack voltage -> warn
    "gravity_tol": 1.5,  # m/s², only checked while nearly still
    "still_gyro": 0.2,  # rad/s
}

SECTIONS = {
    "body": "rt/lf/lowstate",
    "imu2": "rt/lf/secondary_imu",
    "battery": "rt/lf/bmsstate",
    "mainboard": "rt/lf/mainboardstate",
}


def _w(out, level, wid, subsystem, msg):
    out.append({"id": wid, "level": level, "subsystem": subsystem, "msg": msg})


def _band(value, limits, higher_is_bad=True):
    warn, err = limits
    if value is None:
        return None
    if higher_is_bad:
        return "error" if value >= err else "warn" if value >= warn else None
    return "error" if value <= err else "warn" if value <= warn else None


def evaluate(snap, live):
    out = []
    _topics(snap, live, out)
    battery = snap.get("battery")
    body = snap.get("body")
    if body:
        _body(body, battery, out)
    if battery:
        _battery(battery, out)
    if snap.get("mainboard"):
        for i, t in enumerate(snap["mainboard"]["temps"]):
            lvl = _band(t, LIMITS["board_temp"])
            if lvl:
                _w(out, lvl, f"board_temp:{i}", "system", f"Main board sensor {i} at {t} °C")
    for side, hand in (snap.get("hands") or {}).items():
        if hand:
            _hand(side, hand, out)
    order = {"error": 0, "warn": 1, "info": 2}
    out.sort(key=lambda w: order[w["level"]])
    return out


def _topics(snap, live, out):
    for section in ("body", "imu2", "battery", "mainboard"):
        if snap.get(section) is None:
            _w(out, "error", f"missing:{section}", "comms", f"No {section} data received")
    for side in ("left", "right"):
        if (snap.get("hands") or {}).get(side) is None:
            _w(out, "error", f"missing:hand_{side}", "comms", f"No {side} hand data received")
    for topic, st in snap.get("topics", {}).items():
        if st["age_s"] is not None and st["age_s"] > LIMITS["stale_s"]:
            _w(out, "error", f"stale:{topic}", "comms", f"{topic} silent for {st['age_s']:.1f} s")
        expected = layout.LIVE_TOPICS.get(topic, (None, None))[1]
        if live and expected and st["count"] and st["hz"] < LIMITS["rate_frac"] * expected:
            _w(out, "warn", f"rate:{topic}", "comms",
               f"{topic} at {st['hz']:.0f} Hz (expected {expected:.0f})")


def _body(body, battery, out):
    pack_v = battery["voltage"] if battery else None
    for j in body["joints"]:
        name = j["name"]
        if None in (j["q"], j["dq"], j["tau"]):
            _w(out, "error", f"invalid:{name}", "joints", f"{name} reports an invalid number")
        if j["motorstate"]:
            _w(out, "error", f"motorstate:{name}", "joints",
               f"{name} motor status 0x{j['motorstate']:x}")
        t = max(j["temp"])
        lvl = _band(t, LIMITS["body_temp"])
        if lvl:
            _w(out, lvl, f"temp:{name}", "joints", f"{name} at {t} °C")
        if (pack_v and j["i"] not in layout.NO_VOLTAGE_MOTORS and j["vol"] is not None
                and j["vol"] < LIMITS["motor_vol_frac"] * pack_v):
            _w(out, "warn", f"vol:{name}", "power",
               f"{name} supply {j['vol']:.1f} V vs pack {pack_v:.1f} V")
    if body["spare_slots_active"]:
        _w(out, "info", "spare_slots", "joints", "Unused motor slots 31-34 carry data")
    imu = body["imu"]
    if imu and None not in imu["accel"] and None not in imu["gyro"]:
        g = math.sqrt(sum(a * a for a in imu["accel"]))
        still = max(abs(x) for x in imu["gyro"]) < LIMITS["still_gyro"]
        if still and abs(g - 9.81) > LIMITS["gravity_tol"]:
            _w(out, "warn", "imu_gravity", "sensors", f"Main IMU reads {g:.2f} m/s² at rest")


def _battery(b, out):
    lvl = _band(b["soc"], LIMITS["soc"], higher_is_bad=False)
    if lvl:
        _w(out, lvl, "soc", "power", f"Battery at {b['soc']}%")
    lvl = _band(b["cell_spread_mv"], LIMITS["cell_spread_mv"])
    if lvl:
        _w(out, lvl, "cell_spread", "power", f"Cell imbalance {b['cell_spread_mv']} mV")
    t = max(b["temps"]) if b["temps"] else None
    lvl = _band(t, LIMITS["battery_temp"])
    if lvl:
        _w(out, lvl, "battery_temp", "power", f"Battery at {t} °C")


def _hand(side, hand, out):
    sub = f"hand_{side}"
    if any(hand["error"]):
        _w(out, "error", f"{sub}:error", sub, f"{side} hand error {hand['error']}")
    if any(hand["pads_lost"]):
        _w(out, "warn", f"{sub}:pads_lost", sub, f"{side} hand pressure pads lost {sum(hand['pads_lost'])}")
    for m in hand["motors"]:
        if not m["active"]:
            continue
        if m["motorstate"]:
            _w(out, "error", f"{sub}:motorstate:{m['i']}", sub,
               f"{side} hand motor {m['i']} status 0x{m['motorstate']:x}")
        lvl = _band(max(m["temp"]), LIMITS["hand_temp"])
        if lvl:
            _w(out, lvl, f"{sub}:temp:{m['i']}", sub,
               f"{side} hand motor {m['i']} at {max(m['temp'])} °C")
