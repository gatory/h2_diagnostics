"""② Rule-based health checks: snapshot -> warnings.

Only fields marked ✅/🟡 in docs/field_map.md feed rules. All thresholds are
PROVISIONAL guesses until we have baselines from real sessions (PLAN phase 4).
"""
import math

from .. import layout

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
    # Distance (rad) from the nearest joint limit: warn when this close, error when
    # past the limit by more than 0.02 (allows for encoder noise and doc rounding).
    # Knees rest straight ~0.083 rad from their limit, so don't widen the warn zone.
    "joint_margin": (0.05, -0.02),
}

# Hysteresis: once a banded warning is on, it stays on until the value is this far
# back on the good side of the threshold. Stops warnings flickering when a value
# hovers right at a limit (e.g. a motor sitting at 69.9/70.1 °C).
HYSTERESIS = {
    "body_temp": 3,  # °C
    "hand_temp": 3,
    "board_temp": 3,
    "battery_temp": 2,
    "soc": 2,  # %
    "cell_spread_mv": 10,
    "joint_margin": 0.02,  # rad
}

SECTIONS = {
    "body": "rt/lf/lowstate",
    "imu2": "rt/lf/secondary_imu",
    "battery": "rt/lf/bmsstate",
    "mainboard": "rt/lf/mainboardstate",
}


def _w(out, level, wid, subsystem, msg):
    out.append({"id": wid, "level": level, "subsystem": subsystem, "msg": msg})


def _band(value, limits, higher_is_bad=True, prev=None, margin=0):
    """Level for `value` against (warn, err) thresholds, or None if fine.

    `prev` is this warning's level on the previous tick. An active level stays on
    until the value is `margin` back past its threshold (hysteresis).
    """
    warn, err = limits
    if value is None:
        return None
    if not higher_is_bad:  # flip signs so one set of comparisons covers both cases
        value, warn, err = -value, -warn, -err
    err_on = err - margin if prev == "error" else err
    warn_on = warn - margin if prev in ("warn", "error") else warn
    return "error" if value >= err_on else "warn" if value >= warn_on else None


class _Ctx:
    """What every rule needs: the output list plus last tick's levels."""

    def __init__(self, prev):
        self.out = []
        self.prev = prev or {}

    def band(self, wid, subsystem, value, key, msg, higher_is_bad=True):
        """Add warning `wid` if `value` breaks LIMITS[key] (with hysteresis)."""
        lvl = _band(value, LIMITS[key], higher_is_bad,
                    prev=self.prev.get(wid), margin=HYSTERESIS.get(key, 0))
        if lvl:
            _w(self.out, lvl, wid, subsystem, msg)


def evaluate(snap, live, prev=None):
    """Snapshot -> list of warnings, most severe first.

    `prev` maps warning id -> level from the previous call; pass it to get
    hysteresis (Bridge does). Without it every call is judged from scratch.
    """
    ctx = _Ctx(prev)
    out = ctx.out
    _topics(snap, live, out)
    battery = snap.get("battery")
    body = snap.get("body")
    if body:
        _body(body, battery, ctx)
    if battery:
        _battery(battery, ctx)
    if snap.get("mainboard"):
        for i, t in enumerate(snap["mainboard"]["temps"]):
            ctx.band(f"board_temp:{i}", "system", t, "board_temp",
                     f"Main board sensor {i} at {t} °C")
    for side, hand in (snap.get("hands") or {}).items():
        if hand:
            _hand(side, hand, ctx)
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
        if live and expected and st["hz"] is not None and st["hz"] < LIMITS["rate_frac"] * expected:
            _w(out, "warn", f"rate:{topic}", "comms",
               f"{topic} at {st['hz']:.0f} Hz (expected {expected:.0f})")


def _body(body, battery, ctx):
    out = ctx.out
    pack_v = battery["voltage"] if battery else None
    # Linkage joints hold angles only in PR mode (0). Unknown mode (None, older
    # recordings) counts as "not PR": better to skip a check than to false-alarm.
    angles_ok = body.get("mode_pr") == 0
    for j in body["joints"]:
        name = j["name"]
        if None in (j["q"], j["dq"], j["tau"]):
            _w(out, "error", f"invalid:{name}", "joints", f"{name} reports an invalid number")
        if j["motorstate"]:
            _w(out, "error", f"motorstate:{name}", "joints",
               f"{name} motor status 0x{j['motorstate']:x}")
        t = max(j["temp"])
        ctx.band(f"temp:{name}", "joints", t, "body_temp", f"{name} at {t} °C")
        if j["q"] is not None and (angles_ok or j["i"] not in layout.PR_LINKAGE_JOINTS):
            lo, hi = layout.JOINT_LIMITS[j["i"]]
            margin = min(j["q"] - lo, hi - j["q"])  # < 0 means past a limit
            ctx.band(f"limit:{name}", "joints", margin, "joint_margin",
                     f"{name} at {j['q']:+.2f} rad, limits {lo:+.2f}..{hi:+.2f}",
                     higher_is_bad=False)
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


def _battery(b, ctx):
    ctx.band("soc", "power", b["soc"], "soc", f"Battery at {b['soc']}%", higher_is_bad=False)
    ctx.band("cell_spread", "power", b["cell_spread_mv"], "cell_spread_mv",
             f"Cell imbalance {b['cell_spread_mv']} mV")
    t = max(b["temps"]) if b["temps"] else None
    ctx.band("battery_temp", "power", t, "battery_temp", f"Battery at {t} °C")


def _hand(side, hand, ctx):
    out = ctx.out
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
        t = max(m["temp"])
        ctx.band(f"{sub}:temp:{m['i']}", sub, t, "hand_temp",
                 f"{side} hand motor {m['i']} at {t} °C")
