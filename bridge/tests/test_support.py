"""Ground/gantry estimate from knee torque (provisional thresholds, display only)."""
import copy

import pytest

from h2_diagnostics.processing import support
from h2_diagnostics.processing.pipeline import H2Diagnostics
from h2_diagnostics.sources.replay import ReplaySource


@pytest.fixture
def snap(recording):
    return H2Diagnostics(ReplaySource(recording)).tick(1.0)


def with_knees(snap, tau):
    s = copy.deepcopy(snap)
    for j in s["body"]["joints"]:
        if j["name"] in support.KNEES:
            j["tau"] = tau
    return s


def test_the_real_recording_is_on_the_gantry(snap):
    # 2026-11-12 recording: robot hanging, knees ~0 N·m
    assert snap["support_raw"]["state"] == "gantry"
    assert snap["support_raw"]["knee_load_nm"] < support.GROUND_OFF_NM


def test_loaded_knees_mean_ground_with_hysteresis(snap):
    est = support.SupportEstimator()
    assert est.update(with_knees(snap, 8.0))["state"] == "ground"  # 16 N·m summed
    assert est.update(with_knees(snap, 4.0))["state"] == "ground"  # 8: between, holds
    assert est.update(with_knees(snap, 2.0))["state"] == "gantry"  # 4: below off
    assert est.update(with_knees(snap, 4.0))["state"] == "gantry"  # 8: between, holds


def test_unknown_without_body_or_torque(snap):
    est = support.SupportEstimator()
    assert est.update({"body": None}) == {"state": None, "knee_load_nm": None}
    assert est.update(with_knees(snap, None))["state"] is None
