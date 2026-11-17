"""Unit tests for health rules: call evaluate() directly, no replay timing involved."""
import copy

import pytest

from h2diag import health
from h2diag.core import Bridge
from h2diag.sources import ReplaySource


@pytest.fixture
def snap(recording):
    s = Bridge(ReplaySource(recording)).tick(1.0)
    s.pop("warnings")
    return s


def levels(snap, prev=None):
    return {w["id"]: w["level"] for w in health.evaluate(snap, live=False, prev=prev)}


def with_temp(snap, joint, t):
    s = copy.deepcopy(snap)
    s["body"]["joints"][joint]["temp"] = [t, t - 5]
    return s


def test_hysteresis_holds_warning_until_value_clears_margin(snap):
    # Warn at 70 °C, hysteresis 3 °C: once on, stays on until below 67 °C.
    lv = levels(with_temp(snap, 12, 71))
    assert lv["temp:waist_yaw"] == "warn"
    assert levels(with_temp(snap, 12, 69), prev=lv)["temp:waist_yaw"] == "warn"  # held
    assert "temp:waist_yaw" not in levels(with_temp(snap, 12, 69))  # no memory: off
    assert "temp:waist_yaw" not in levels(with_temp(snap, 12, 66), prev=lv)  # cleared


def test_hysteresis_steps_error_down_to_warn(snap):
    lv = levels(with_temp(snap, 12, 86))
    assert lv["temp:waist_yaw"] == "error"
    assert levels(with_temp(snap, 12, 83), prev=lv)["temp:waist_yaw"] == "error"  # 85-3=82
    assert levels(with_temp(snap, 12, 81), prev=lv)["temp:waist_yaw"] == "warn"


def test_hysteresis_for_lower_is_bad_values(snap):
    # SoC: warn at <=20 %, hysteresis 2 %: once on, stays on until above 22 %.
    s = copy.deepcopy(snap)
    s["battery"]["soc"] = 20
    lv = levels(s)
    assert lv["soc"] == "warn"
    s["battery"]["soc"] = 22
    assert levels(s, prev=lv)["soc"] == "warn"
    s["battery"]["soc"] = 23
    assert "soc" not in levels(s, prev=lv)


def test_resting_knees_do_not_warn(snap):
    # Knees stand ~0.083 rad from their straight limit; that must stay quiet.
    assert not any(k.startswith("limit:") for k in levels(snap))
