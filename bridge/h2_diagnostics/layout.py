"""What the H2 publishes and how its slots are named. See docs/field_map.md."""

# Joint order 0..30. Indices 12-14 and the wrists follow the majority of Unitree's
# examples (C++ examples + Python arm_sdk example). Unverified on our robot until
# field-map test T1; the snapshot carries JOINT_ORDER_VERIFIED so the UI can say so.
JOINT_ORDER_VERIFIED = False
BODY_JOINTS = [
    "L_hip_pitch", "L_hip_roll", "L_hip_yaw", "L_knee", "L_ankle_roll", "L_ankle_pitch",
    "R_hip_pitch", "R_hip_roll", "R_hip_yaw", "R_knee", "R_ankle_roll", "R_ankle_pitch",
    "waist_yaw", "waist_roll", "waist_pitch",
    "L_shoulder_pitch", "L_shoulder_roll", "L_shoulder_yaw", "L_elbow",
    "L_wrist_roll", "L_wrist_pitch", "L_wrist_yaw",
    "R_shoulder_pitch", "R_shoulder_roll", "R_shoulder_yaw", "R_elbow",
    "R_wrist_roll", "R_wrist_pitch", "R_wrist_yaw",
    "head_pitch", "head_yaw",
]
NUM_BODY = len(BODY_JOINTS)  # 31; LowState_ has 35 slots, 31..34 are unused

# Joint position limits (rad), (min, max) per joint in BODY_JOINTS order. From
# Unitree's "H2 Full Body Joint Motor Order" table. Left/right roll joints mirror.
JOINT_LIMITS = [
    (-2.4525975, 2.7754225), (-0.467441, 2.1688605), (-2.827, 2.827),                          # L hip p/r/y
    (-0.08725, 2.53025), (-0.3490658503, 0.296705972783), (-1.13446401358, 0.61086523808),     # L knee, ankle r/p
    (-2.4525975, 2.7754225), (-2.1688605, 0.467441), (-2.827, 2.827),                          # R hip p/r/y
    (-0.08725, 2.53025), (-0.296705972783, 0.3490658503), (-1.13446401358, 0.61086523808),     # R knee, ankle r/p
    (-1.7453, 1.7453), (-0.5236, 0.5236), (-0.43633, 0.5236),                                  # waist y/r/p
    (-2.6179939, 1.8325957), (-0.517, 2.494), (-2.6179939, 2.6179939), (-0.986111, 3.0717795), # L shoulder p/r/y, elbow
    (-2.6179939, 2.6179939), (-0.576, 0.576), (-1.2217305, 1.2217305),                         # L wrist r/p/y
    (-2.6179939, 1.8325957), (-2.494, 0.517), (-2.6179939, 2.6179939), (-0.986111, 3.0717795), # R shoulder p/r/y, elbow
    (-2.6179939, 2.6179939), (-0.576, 0.576), (-1.2217305, 1.2217305),                         # R wrist r/p/y
    (-0.5236, 0.83775), (-1.7453, 1.7453),                                                     # head p/y
]
assert len(JOINT_LIMITS) == NUM_BODY

# Parallel-linkage joints (two motors via rods). With mode_pr == 1 ("AB") their
# slots hold raw motor A/B positions, not joint angles, so angle limits don't apply.
PR_LINKAGE_JOINTS = frozenset({4, 5, 10, 11, 13, 14})

# Leg motors that report mode 10 and always vol == 0 (a different motor family).
NO_VOLTAGE_MOTORS = frozenset({0, 1, 2, 3, 6, 7, 8, 9})

HAND_ACTIVE_MOTORS = 16  # Dex5: slots 0..15 active, 16..19 report q only
HAND_PRESSURE_CELLS = 6  # of the 12 per pad, only the first 6 carry data
BMS_CELLS = 18

# Role -> topics that can fill it, in preference order. Live mode subscribes to
# the first one; replay accepts any (older recordings used the 1 kHz topics).
ROLES = {
    "body": ("rt/lf/lowstate", "rt/lowstate"),
    "imu2": ("rt/lf/secondary_imu", "rt/secondary_imu"),
    "battery": ("rt/lf/bmsstate",),
    "mainboard": ("rt/lf/mainboardstate",),
    "hand_left": ("rt/dex5/left/state",),
    "hand_right": ("rt/dex5/right/state",),
}
TOPIC_ROLE = {t: role for role, topics in ROLES.items() for t in topics}

# Live subscriptions: topic -> (unitree_hg type name, expected Hz measured on the Thor)
LIVE_TOPICS = {
    "rt/lf/lowstate": ("LowState_", 20.0),
    "rt/lf/secondary_imu": ("IMUState_", 20.0),
    "rt/lf/bmsstate": ("BmsState_", 20.0),
    "rt/lf/mainboardstate": ("MainBoardState_", 20.0),
    "rt/dex5/left/state": ("HandState_", 100.0),
    "rt/dex5/right/state": ("HandState_", 100.0),
}
