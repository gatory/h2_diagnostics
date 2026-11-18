"""② Raw messages -> the normalized snapshot (named joints, SI units, topic stats).

Keeps the newest message per role; decoding happens only when a snapshot is built.
"""
from .. import layout
from ..sources.convert import num


class RobotState:
    """Holds the newest decoded message for each role and builds snapshots."""

    def __init__(self, stats):
        self.stats = stats  # {topic: TopicStats}, owned and updated by the source
        self.latest = {}  # role -> (topic, data dict)

    def ingest(self, topic, data):
        role = layout.TOPIC_ROLE.get(topic)
        if role is not None:
            self.latest[role] = (topic, data)

    def snapshot(self, now, wall_time, source):
        get = lambda role: self.latest.get(role, (None, None))[1]
        body = get("body")
        return {
            "t": round(wall_time, 3),
            "source": source,
            "joint_order_verified": layout.JOINT_ORDER_VERIFIED,
            # expected_hz comes from layout so the dashboard needn't copy the rates
            # (None for topics outside LIVE_TOPICS, e.g. an old recording's rt/lowstate)
            "topics": {t: {**s.report(now), "expected_hz": layout.LIVE_TOPICS.get(t, (None, None))[1]}
                       for t, s in self.stats.items()},
            "body": _body(body),
            # Both IMUs side by side, like the hands. The pelvis one arrives inside
            # LowState_ (rt/lf/lowstate), the torso one on its own topic (T1).
            "imu": {
                "pelvis": _imu(body["imu_state"]) if body else None,
                "torso": _imu(get("torso_imu")),
            },
            "mode": _mode(),
            "battery": _battery(get("battery")),
            "mainboard": _mainboard(get("mainboard")),
            "hands": {"left": _hand(get("hand_left")), "right": _hand(get("hand_right"))},
        }


def _mode():
    """The robot's locomotion FSM state (damp, stand_up, start, ...; layout.FSM_STATES).

    Placeholder until test T6: switching modes with the remote while recording will
    show which field tracks the FSM, LowState_.mode_machine (already in "body") or
    rt/odommodestate's "mode". Until then the id is None rather than a guess, and the
    `_raw` names mean "unconfirmed: display with ?, never warn on it".
    """
    fsm_id = None  # T6: set from the confirmed field
    return {"fsm_id_raw": fsm_id, "fsm_name_raw": layout.FSM_STATES.get(fsm_id)}


def _imu(d):
    if not d:
        return None
    return {
        "quat": [num(v) for v in d["quaternion"]],
        "gyro": [num(v) for v in d["gyroscope"]],
        "accel": [num(v) for v in d["accelerometer"]],
        "rpy": [num(v) for v in d["rpy"]],
        "temp_raw": d.get("temperature"),  # meaning unclear (field map ❓)
    }


def _motor(m):
    return {
        "q": num(m["q"]),
        "dq": num(m["dq"]),
        "tau": num(m["tau_est"]),
        "temp": list(m["temperature"]),
        "vol": num(m["vol"], 2),
        "mode": m["mode"],
        "motorstate": m["motorstate"],
    }


def _body(d):
    if not d:
        return None
    motors = d["motor_state"]
    joints = []
    for i, name in enumerate(layout.BODY_JOINTS):
        j = _motor(motors[i])
        j.update(i=i, name=name)
        joints.append(j)
    spare = motors[layout.NUM_BODY:]
    return {
        "joints": joints,
        "mode_machine": d.get("mode_machine"),
        "mode_pr": d.get("mode_pr"),
        "tick": d.get("tick"),
        "spare_slots_active": any(m["mode"] or m["q"] for m in spare),
    }


def _battery(d):
    if not d:
        return None
    cells = [c / 1000.0 for c in d["cell_vol"][: layout.BMS_CELLS]]
    live = [c for c in cells if c > 0]
    return {
        "soc": d["soc"],
        "soh": d["soh"],
        "voltage": num(d["bmsvoltage"][0] / 1000.0, 2),
        "current_raw": d["current"],  # probably mA, negative = discharge (field map 🟡)
        "cells": [num(c, 3) for c in cells],
        "cell_spread_mv": round((max(live) - min(live)) * 1000) if live else None,
        "temps": d["temperature"][:5],
        "cycles": d["cycle"],
        "state_raw": d["bmsstate"],
    }


def _mainboard(d):
    if not d:
        return None
    return {"temps": d["temperature"][:4], "fans": d["fan_state"], "state": d["state"]}


def _hand(d):
    if not d:
        return None
    motors = []
    for i, m in enumerate(d["motor_state"]):
        h = _motor(m)
        h.update(i=i, active=i < layout.HAND_ACTIVE_MOTORS)
        motors.append(h)
    pressure = [
        [num(v, 1) for v in pad["pressure"][: layout.HAND_PRESSURE_CELLS]]
        for pad in d["press_sensor_state"]
    ]
    imu = d["imu_state"]
    return {
        "motors": motors,
        "pressure": pressure,
        "pads_lost": [pad["lost"] for pad in d["press_sensor_state"]],
        "gyro": [num(v) for v in imu["gyroscope"]],
        "accel": [num(v) for v in imu["accelerometer"]],
        "imu_temp_raw": imu["temperature"],
        "error": d["error"],
        "power_v_raw": num(d["power_v"], 3),
        "power_a_raw": num(d["power_a"], 3),
    }
