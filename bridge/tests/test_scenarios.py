"""Health rules against fake faults injected into a real recording."""
from h2diag.data.replay import ReplaySource
from h2diag.processing import preflight


def run(path):
    return preflight.run(ReplaySource(path), seconds=60, realtime=False)


def ids(rep):
    return {w["id"]: w["level"] for w in rep["findings"]}


def on_topic(topic, fn):
    def mutate(rec):
        if rec["topic"] == topic:
            fn(rec)
        return rec
    return mutate


def test_healthy_recording_passes(recording):
    rep = run(recording)
    assert rep["verdict"] == "PASS", rep["findings"]
    assert rep["summary"]["hottest_joint"].startswith("waist_yaw")


def test_motor_error_code(scenario):
    def f(rec):
        rec["data"]["motor_state"][3]["motorstate"] = 0x20
    rep = run(scenario("motor_code", on_topic("rt/lowstate", f)))
    assert ids(rep)["motorstate:L_knee"] == "error"
    assert rep["verdict"] == "FAIL"


def test_nan_joint(scenario):
    def f(rec):
        rec["data"]["motor_state"][18]["q"] = None  # NaN is stored as null
    rep = run(scenario("nan_joint", on_topic("rt/lowstate", f)))
    assert ids(rep)["invalid:L_elbow"] == "error"


def test_hot_joint_warn_and_error(scenario):
    def f(rec):
        rec["data"]["motor_state"][9]["temperature"] = [72, 60]
        rec["data"]["motor_state"][10]["temperature"] = [90, 70]
    found = ids(run(scenario("hot", on_topic("rt/lowstate", f))))
    assert found["temp:R_knee"] == "warn"
    assert found["temp:R_ankle_roll"] == "error"


def test_stalled_stream(scenario):
    rep = run(scenario("stalled", lambda r: None if r["topic"] == "rt/lf/bmsstate" and r["t"] > 0.8 else r))
    assert ids(rep)["stale:rt/lf/bmsstate"] == "error"


def test_missing_hand(scenario):
    rep = run(scenario("no_hand", lambda r: None if r["topic"] == "rt/dex5/right/state" else r))
    assert ids(rep)["missing:hand_right"] == "error"


def test_battery_low_and_imbalanced(scenario):
    def f(rec):
        rec["data"]["soc"] = 8
        rec["data"]["cell_vol"][5] -= 120
    found = ids(run(scenario("battery", on_topic("rt/lf/bmsstate", f))))
    assert found["soc"] == "error"
    assert found["cell_spread"] == "error"


def test_hand_error_and_hot_motor(scenario):
    def f(rec):
        rec["data"]["error"] = [1, 0]
        rec["data"]["motor_state"][4]["temperature"] = [80, 0]
        rec["data"]["motor_state"][17]["temperature"] = [99, 0]  # inactive slot: ignored
    found = ids(run(scenario("hand", on_topic("rt/dex5/left/state", f))))
    assert found["hand_left:error"] == "error"
    assert found["hand_left:temp:4"] == "warn"
    assert "hand_left:temp:17" not in found


def test_leg_motor_zero_voltage_is_normal(recording):
    # Leg motors 0-3, 6-9 always report vol 0; they must not raise voltage warnings.
    assert not any(i.startswith("vol:") for i in ids(run(recording)))


def test_joint_past_limit_and_near_limit(scenario):
    def f(rec):
        rec["data"]["motor_state"][3]["q"] = -0.2  # L_knee: 0.11 rad past its -0.087 limit
        rec["data"]["motor_state"][25]["q"] = 3.05  # R_elbow: 0.02 rad inside its 3.07 limit
    found = ids(run(scenario("limits", on_topic("rt/lowstate", f))))
    assert found["limit:L_knee"] == "error"
    assert found["limit:R_elbow"] == "warn"


def test_linkage_joints_skipped_in_ab_mode(scenario):
    # mode_pr 1 = AB: ankle/waist slots hold raw motor positions, not angles.
    def f(rec):
        rec["data"]["mode_pr"] = 1
        rec["data"]["motor_state"][5]["q"] = 1.5  # L_ankle_pitch: way out as an angle
        rec["data"]["motor_state"][3]["q"] = -0.2  # L_knee is not a linkage joint
    found = ids(run(scenario("ab_mode", on_topic("rt/lowstate", f))))
    assert "limit:L_ankle_pitch" not in found
    assert found["limit:L_knee"] == "error"
