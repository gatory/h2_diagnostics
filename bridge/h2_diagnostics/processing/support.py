"""② Is the robot standing on the ground, or hanging in the gantry? (UNCONFIRMED)

The IMU can't tell: it sees the same tilt and gravity either way. The leg motors can.
Standing, the knees carry the body's weight; hanging, they only carry the lower leg.
So the estimate is the summed |estimated torque| of both knees (`tau_est`).

The knees are used because they are plain motors. The ankles are parallel-linkage
joints, whose slots hold raw motor A/B values in mode_pr 1 (AB).

THRESHOLDS ARE PROVISIONAL. Every recording so far (2026-11-12, T1, T2) is on the
gantry: knees within about ±1.5 N·m each, even while the legs were moved by hand.
There is no recording on the ground yet. A standing robot with bent knees should be at
tens of N·m, but with nearly straight knees the load passes through the joint and the
torque can stay small. Record standing on the ground to set these, then drop `_raw`.

The result is display only (the dashboard picks its frame from it), never a warning.
"""
from .. import layout

GROUND_ON_NM = 10.0  # summed knee |tau| above this -> "ground"
GROUND_OFF_NM = 5.0  # ... and back to "gantry" only below this (hysteresis: no flicker)
KNEES = ("L_knee", "R_knee")


class SupportEstimator:
    """Ground/gantry with hysteresis; remembers the last state between ticks."""

    def __init__(self):
        self.state = None  # None until the first body message

    def update(self, snap):
        load = knee_load(snap.get("body"))
        if load is None:
            self.state = None
        elif load > GROUND_ON_NM:
            self.state = "ground"
        elif load < GROUND_OFF_NM or self.state is None:
            self.state = "gantry"
        # in between: keep the previous state
        return {"state": self.state, "knee_load_nm": None if load is None else round(load, 2)}


def knee_load(body):
    """Summed |tau| of both knees, or None without body data or with an invalid torque."""
    if not body:
        return None
    by_name = {j["name"]: j for j in body["joints"]}
    taus = [by_name[k]["tau"] for k in KNEES if k in by_name]
    if len(taus) != len(KNEES) or any(t is None for t in taus):
        return None
    return sum(abs(t) for t in taus)


assert all(k in layout.BODY_JOINTS for k in KNEES)
