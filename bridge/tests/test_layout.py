"""layout.py's tables must agree with each other, and with the dashboard's H2.urdf."""
import xml.etree.ElementTree as ET
from pathlib import Path

from h2_diagnostics import layout


def test_every_live_topic_is_a_roles_first_choice():
    # LIVE_TOPICS and ROLES are two views of the same six topics. If one is edited
    # without the other, LiveSource subscribes to a topic that ingest() then drops
    # (or a role waits for a topic nobody subscribes to).
    first_choices = {topics[0] for topics in layout.ROLES.values()}
    assert first_choices == set(layout.LIVE_TOPICS)


def test_no_topic_fills_two_roles():
    # TOPIC_ROLE is built with a dict comprehension: a topic listed under two roles
    # would silently keep only the last one.
    all_topics = [t for topics in layout.ROLES.values() for t in topics]
    assert len(all_topics) == len(set(all_topics))
    assert len(layout.TOPIC_ROLE) == len(all_topics)


def test_fsm_states_are_the_h2_ids():
    # From h2_loco_client.hpp. "start" is the H2-specific one (the G1 uses 500).
    assert layout.FSM_STATES[1] == "damp"
    assert layout.FSM_STATES[601] == "start"
    assert 500 not in layout.FSM_STATES


# --- The dashboard's 3D model must describe the same robot as layout.py --------
# The URDF names joints its own way (L_hip_pitch -> left_hip_pitch_joint) and lists
# them in its own file order (head before arms), so the dashboard maps by NAME.
# This test catches a renamed joint or a changed limit on either side.
H2_URDF = Path(__file__).resolve().parents[2] / "dashboard/h2_renders/h2_description/H2.urdf"


def urdf_joint_name(name):
    """layout name -> URDF name: L_/R_ prefix becomes left_/right_, plus _joint."""
    for short, long in (("L_", "left_"), ("R_", "right_")):
        if name.startswith(short):
            name = long + name[len(short):]
    return name if name.endswith("_joint") else name + "_joint"


def test_urdf_has_every_layout_joint_with_the_same_limits():
    joints = {j.get("name"): j for j in ET.parse(H2_URDF).getroot().iter("joint")
              if j.get("type") != "fixed"}
    assert len(joints) == layout.NUM_BODY  # 31 moving joints, none extra
    for name, lo, hi in layout.JOINTS:
        j = joints.get(urdf_joint_name(name))
        assert j is not None, f"{name}: no {urdf_joint_name(name)} in H2.urdf"
        limit = j.find("limit")
        # 0.005 rad tolerance: the URDF rounds wrist_yaw to 1.22 (layout: 1.2217)
        assert abs(float(limit.get("lower")) - lo) < 0.005, name
        assert abs(float(limit.get("upper")) - hi) < 0.005, name


def test_urdf_puts_the_imus_where_t1_found_them():
    # T1 (2026-11-17) found the main IMU in the pelvis and secondary_imu in the torso.
    parents = {j.find("child").get("link"): j.find("parent").get("link")
               for j in ET.parse(H2_URDF).getroot().iter("joint")}
    assert parents["imu_in_pelvis"] == "pelvis"
    assert parents["imu_in_torso"] == "torso_link"
