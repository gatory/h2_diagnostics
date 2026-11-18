"""What the H2 publishes and how its slots are named. See docs/field_map.md."""

# Body joints in slot order: row i is LowState_.motor_state[i]. Order matches SDK2
# C++ H2JointIndex; T1 (2026-11-17) confirmed waist 12-14 and wrist slots 19/21,
# 26/28. Slots 20/27 not yet seen moving, so JOINT_ORDER_VERIFIED stays False
# (the snapshot carries it so the UI can say so).
# Limits (rad) are from Unitree's "H2 Full Body Joint Motor Order" table;
# left/right roll joints mirror.
JOINT_ORDER_VERIFIED = False
JOINTS = [
    # name               min (rad)        max (rad)        slot
    ("L_hip_pitch",      -2.4525975,      2.7754225),      # 0
    ("L_hip_roll",       -0.467441,       2.1688605),      # 1
    ("L_hip_yaw",        -2.827,          2.827),          # 2
    ("L_knee",           -0.08725,        2.53025),        # 3
    ("L_ankle_roll",     -0.3490658503,   0.296705972783), # 4
    ("L_ankle_pitch",    -1.13446401358,  0.61086523808),  # 5

    ("R_hip_pitch",      -2.4525975,      2.7754225),      # 6
    ("R_hip_roll",       -2.1688605,      0.467441),       # 7
    ("R_hip_yaw",        -2.827,          2.827),          # 8
    ("R_knee",           -0.08725,        2.53025),        # 9
    ("R_ankle_roll",     -0.296705972783, 0.3490658503),   # 10
    ("R_ankle_pitch",    -1.13446401358,  0.61086523808),  # 11

    ("waist_yaw",        -1.7453,         1.7453),         # 12
    ("waist_roll",       -0.5236,         0.5236),         # 13
    ("waist_pitch",      -0.43633,        0.5236),         # 14

    ("L_shoulder_pitch", -2.6179939,      1.8325957),      # 15
    ("L_shoulder_roll",  -0.517,          2.494),          # 16
    ("L_shoulder_yaw",   -2.6179939,      2.6179939),      # 17
    ("L_elbow",          -0.986111,       3.0717795),      # 18
    ("L_wrist_roll",     -2.6179939,      2.6179939),      # 19
    ("L_wrist_pitch",    -0.576,          0.576),          # 20
    ("L_wrist_yaw",      -1.2217305,      1.2217305),      # 21

    ("R_shoulder_pitch", -2.6179939,      1.8325957),      # 22
    ("R_shoulder_roll",  -2.494,          0.517),          # 23
    ("R_shoulder_yaw",   -2.6179939,      2.6179939),      # 24
    ("R_elbow",          -0.986111,       3.0717795),      # 25
    ("R_wrist_roll",     -2.6179939,      2.6179939),      # 26
    ("R_wrist_pitch",    -0.576,          0.576),          # 27
    ("R_wrist_yaw",      -1.2217305,      1.2217305),      # 28

    ("head_pitch",       -0.5236,         0.83775),        # 29
    ("head_yaw",         -1.7453,         1.7453),         # 30
]

BODY_JOINTS = [name for name, lo, hi in JOINTS]
JOINT_LIMITS = [(lo, hi) for name, lo, hi in JOINTS]
NUM_BODY = len(JOINTS)  # 31; LowState_ has 35 slots, 31..34 are unused

# TODO: check this yourself later
# Parallel-linkage joints (two motors via rods). With mode_pr == 1 ("AB") their
# slots hold raw motor A/B positions, not joint angles, so angle limits don't apply.
PR_LINKAGE_JOINTS = frozenset({4, 5, 10, 11, 13, 14})

# TODO: check this yourself later
# Leg motors that report mode 10 and always vol == 0 (a different motor family).
NO_VOLTAGE_MOTORS = frozenset({0, 1, 2, 3, 6, 7, 8, 9})

# TODO: check this yourself later
HAND_ACTIVE_MOTORS = 16  # Dex5: slots 0..15 active, 16..19 report q only
HAND_PRESSURE_CELLS = 6  # of the 12 per pad, only the first 6 carry data
BMS_CELLS = 18

# Role -> topics that can fill it.
# The first one is the live topic: it must be in LIVE_TOPICS (tests/test_layout.py checks).
# Replay accepts any of them (older recordings used the 1 kHz topics).
ROLES = {
    "body": ("rt/lf/lowstate", "rt/lowstate"),
    "torso_imu": ("rt/lf/secondary_imu", "rt/secondary_imu"),  # pelvis IMU rides in "body" (lowstate topic)
    "battery": ("rt/lf/bmsstate",),
    "mainboard": ("rt/lf/mainboardstate",),
    "hand_left": ("rt/dex5/left/state",),
    "hand_right": ("rt/dex5/right/state",),
}
# Topic -> role
TOPIC_ROLE = {t: role for role, topics in ROLES.items() for t in topics}

# Live Subscription Topics -> (unitree_hg type name, expected Hz measured on the Thor)
# The master list: LiveSource subscribes to these, health checks their rates, and
# sources/probe.py builds `rates --set bridge` from it. Add a topic here (and its role above).
LIVE_TOPICS = {
    "rt/lf/lowstate": ("LowState_", 20.0),
    "rt/lf/secondary_imu": ("IMUState_", 20.0),
    "rt/lf/bmsstate": ("BmsState_", 20.0),
    "rt/lf/mainboardstate": ("MainBoardState_", 20.0),
    "rt/dex5/left/state": ("HandState_", 100.0),
    "rt/dex5/right/state": ("HandState_", 100.0),
}

# Locomotion FSM (finite-state machine) states: id -> name. From the H2 loco client in
# the C++ SDK (unitree_sdk2/include/unitree/robot/h2/loco/h2_loco_client.hpp:242-252).
# H2-specific: "start" is 601 here but 500 on the G1. The robot may know more ids
# (GetAvailableFsmIds, API 7008, would list them, but asking means publishing).
# Which received field carries the current id is not known yet: test T6 decides.
FSM_STATES = {
    0: "zero_torque",
    1: "damp",
    2: "squat",
    3: "sit",
    4: "stand_up",
    601: "start",
}
