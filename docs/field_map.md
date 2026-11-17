# H2 Field Map

What each telemetry field means, how sure we are, and how to confirm the rest.

- **Sources:** the SDK message definitions (`unitree_sdk2py/idl/unitree_hg`), the Unitree H2 examples, and two files now in `bridge/tests/data/`:
  - `topics_20261113.json`: a single sample per topic
  - `sensors_20261112_150110.jsonl`: 2 s of a robot standing still
- **Confidence:**
  - ✅ confirmed from data
  - 🟡 likely; needs a check on the robot
  - ❓ unknown; the dashboard shows the raw value and doesn't use it for warnings

## Rule: H2-specific, confirmed topics only

Unitree runs one software stack across its robots, so this H2 publishes topics meant for other models:
- quadruped topics: `rt/dog_odom`, `rt/dog_imu_raw`, `rt/odommodestate` (`unitree_go` types)
- Dex3 topics, which is the G1's hand: `rt/api/dex3_msg_controller`
- `rt/wirelesscontroller`

A topic existing doesn't mean it carries meaningful data. **The bridge only uses `unitree_hg` topics whose contents have been checked against physics or a robot test.** That means the table below. A topic gets added only after a test shows what it means on the H2.

## Topics the bridge uses

| Topic | Type | Rate (measured on the Thor) |
|---|---|---|
| `rt/lf/lowstate` | `LowState_` | 20 Hz |
| `rt/lf/secondary_imu` | `IMUState_` (**in the torso**, above the waist; T1) | 20 Hz |
| `rt/lf/bmsstate` | `BmsState_` | 20 Hz |
| `rt/lf/mainboardstate` | `MainBoardState_` | 20 Hz |
| `rt/dex5/left/state`, `rt/dex5/right/state` | `HandState_` | 100 Hz |
| `rt/lf/sportmodestate` | `unitree_hg SportModeState_` | ❓ The SDK has no message definition for it; we need to write one. It probably carries the robot's mode and gait. |
| `rt/lowcmd` | `LowCmd_` | 1 kHz. Commanded position for tracking error. Too fast for Python; see PLAN risks. Was publishing during the 2026-11-17 discovery (634 Hz measured under full-discovery load), so a controller was active. |

`rt/lf/secondary_bmsstate` exists but is silent (a second battery that isn't fitted?).

**2026-11-17 discovery (`h2diag topics`, 124 topics; saved on the Thor in `results/discovery/topics_20261117_134607.*`).** Candidates worth a look, not used yet:
- `rt/arm/action/state` (`std_msgs String`, 4.3 Hz) and `rt/rtc/state` (String, 1 Hz): readable text, possibly the robot's mode/action state. That could stand in for the undecodable `sportmodestate` on the status strip.
- `rt/api/sport/*` and `rt/api/robot_state/*` request/response pairs at ~1.9 Hz: something on the robot polls these services.
- `rt/arm_sdk` (`LowCmd_`) exists but was silent.

Note: discovery samples every topic at once, which overloads Python, so its rates read low (`rt/lf/*` showed 10 Hz). Use `h2diag rates` for true rates (`rt/lf/*` 20.3 Hz).

## Body: `LowState_`

| Field | Meaning | Confidence |
|---|---|---|
| `motor_state[0..30]` | The 31 joints, in the order below | ✅ count / ✅ order for 12–14, 19, 21, 26, 28 (T1) / 🟡 slots 20 and 27 not yet seen moving |
| `motor_state[31..34]` | Unused: always zero | ✅ |
| `mode_machine` | Robot type or control mode; it was 1 in both recordings | ❓ |
| `mode_pr` | Ankle and waist control mode: 0 = pitch/roll (series), 1 = A/B (parallel), per the C++ example | 🟡 |
| `tick` | Counter from the robot's controller, useful for spotting dropped messages | 🟡 |
| `crc` | CRC32 over the message; the C++ example has the algorithm | ✅ |
| `imu_state.*` | Main IMU, **in the pelvis** (below the waist; T1, see below): quaternion (w, x, y, z), gyro (rad/s), accel (m/s², ≈9.87 at rest ✅), rpy (rad) | ✅ |
| `imu_state.temperature` | Constant 79 | ❓ Is it °C? It's suspiciously high and never changes. |
| `wireless_remote[40]` | Raw bytes from the handheld remote | 🟡 |

### Joint order: Unitree's own examples disagree

| Index | C++ examples + Python `arm_sdk` example (3 of 4) | Python `ankle_swing` example, which `common.py` copied |
|---|---|---|
| 12 / 13 / 14 | waist **yaw** / roll / pitch | waist **roll** / pitch / yaw |
| 19 / 20 / 21 (L), 26 / 27 / 28 (R) | wrist **roll** / pitch / yaw | wrist **yaw** / pitch / roll |

Indices 0–11 (legs), 15–18 and 22–25 (shoulders, elbows), and 29–30 (head pitch, yaw) agree everywhere. `common.py`'s labels for 12–14 and the wrists are wrong.

### T1 result (2026-11-17, `20261117_135149_t1_joints.jsonl.gz`)

The majority order (left column above, `layout.py`) is right where it could be checked. Markers in this recording were typed *after* each movement, so each burst of motion belongs to the marker that follows it.

| Slot | Name in `layout.py` | Evidence | Status |
|---|---|---|---|
| 12 | waist_yaw | Moved alone during the waist-yaw movement. It tracks the yaw between the two IMUs with a 2° residual. | ✅ |
| 13 | waist_roll | Tracks the roll between the IMUs: correlation 0.95, slope 1.06 (10° IMU vs 11° joint) | ✅ |
| 14 | waist_pitch | Tracks the pitch between the IMUs: correlation 0.93, slope 0.86 (27° vs 27°) | ✅ |
| 19 / 26 | L / R wrist_roll | Moved alone during wrist roll; slot 19 reached its −2.62 limit | ✅ |
| 21 / 28 | L / R wrist_yaw | Moved alone (~1.8 rad, reaching the +1.22 limit) when the hand was **bent toward the palm / back of the hand** | ✅ slot, see note |
| 20 / 27 | L / R wrist_pitch | Never moved more than 0.4 rad. The "wrist yaw" attempt twisted the forearm and mostly moved shoulder yaw (17 / 24). | 🟡 not yet seen |

**Waist roll and pitch were too stiff to move cleanly by hand,** so they were checked a different way. The main IMU and `secondary_imu` sit on opposite sides of the waist, so the rotation between them *is* the waist rotation. The relative rotation (main → secondary) is computed from the quaternions, waist yaw (slot 12) is removed, and the remaining roll/pitch is compared with slots 13/14. Only "main IMU = pelvis, secondary = torso" fits: the reverse leaves a 50° yaw residual. Naive Euler-angle subtraction gives a misleading answer (it suggested 13/14 were swapped), because roll and pitch mix once the waist is yawed.

**Wrist naming:** the hand bending toward the palm / back of the hand (what a person calls wrist pitch) is slot 21/28, which Unitree's table names **wrist_yaw**. Each slot's limits fit the motion that slot made: 21/28 have the wide ±1.22 range, and 20/27 the narrow ±0.58 range, which fits side-to-side bending. So we keep Unitree's names (the URDF will use them) and note the physical motion. Still to do: see slot 20/27 move (bend the hand thumb-ward / pinky-ward without twisting the forearm).

**Waist yaw goes past its listed limit:** slot 12 reached −2.22 … +2.45 rad by hand, while Unitree's table gives ±1.75. The IMUs confirm the waist really turned that far, so ±1.75 is probably a software limit rather than a mechanical stop. Until that's settled, the health check will raise waist_yaw limit errors whenever the waist is turned that far by hand.

### Per motor: `MotorState_`

| Field | Meaning | Confidence |
|---|---|---|
| `q`, `dq`, `ddq` | Position (rad), velocity (rad/s), acceleration (always 0) | ✅ / ✅ / ✅ unused |
| `tau_est` | Estimated torque (N·m) | 🟡 |
| `temperature[0]`, `[1]` | Two sensors. `[0]` ≥ `[1]` always, so probably winding vs. housing (°C). Range 25–53 at rest. | 🟡 |
| `vol` | Supply voltage (V). It's 72.5 when the battery reads 72.9 V. Always **0 on the leg motors 0–3 and 6–9**. | ✅ |
| `mode` | **10** on leg motors 0–3 and 6–9, **1** on all others, **0** in unused slots. Looks like the motor or driver family rather than on/off. | 🟡 |
| `sensor[0]` | Non-zero only on ankles (1, ~126) and shoulder roll/yaw, elbow and slot 19/26 (~185) | ❓ |
| `motorstate` | Error/status bits; 0 everywhere so far | 🟡 meaning of each bit ❓ |
| `reserve[1]` | ~1142–1151, shared across motors. A firmware build or counter? | ❓ |
| `reserve[2]` | 6 on the mode-10 motors, 5 on the others; matches the family split | 🟡 |

**Two motor families:** leg motors 0–3 and 6–9 (hip pitch/roll/yaw and knee) report `mode` 10, `vol` 0 and `reserve[2]` 6. Every other motor reports `mode` 1, a real `vol` and `reserve[2]` 5. The dashboard needs to treat "voltage 0" as normal for those 8 motors.

**At rest the 2026-11-12 recording showed a hot group at 48–53 °C:**
- waist 12–14
- shoulder pitch 15 and 22
- slots 20, 21, 27 and 28 (wrists)

Everything else was 25–42 °C. The heat may come from holding the pose against gravity; T3 checks this.

## Battery: `BmsState_` (`rt/lf/bmsstate`)

| Field | Meaning | Confidence |
|---|---|---|
| `cell_vol[0..17]` | 18 cells in mV; `[18..39]` unused | ✅ They sum to `bmsvoltage[0]`. |
| `bmsvoltage[0]`, `[1]` | Pack voltage in mV, from two measurements | ✅ |
| `current` | -3164 at rest. Probably mA, with negative meaning discharge (~3 A, ~230 W idle). | 🟡 T4 checks this. |
| `soc`, `soh` | Charge % and health % | ✅ |
| `temperature[0..4]` | °C (21–32); `[5..11]` unused | 🟡 |
| `cycle` | Charge cycles (5) | ✅ |
| `bmsstate[5]` | `[577, 0, 0, 0, 18]` both times. 18 = cell count? | ❓ |
| `fn`, `version_*` | 120, v1.12 | ❓ / ✅ |

## Main board: `MainBoardState_`

| Field | Meaning | Confidence |
|---|---|---|
| `temperature[0..3]` | °C: 49, 56, 55, 30. Which board parts these are is unknown. | 🟡 |
| `fan_state[6]` | All 0. Fans off, or not reported? | ❓ |
| `state[0]` | 1 | ❓ |
| `value[6]` | All 0 | ❓ |

## Hands: `HandState_` (Dex5)

| Field | Meaning | Confidence |
|---|---|---|
| `motor_state[0..15]` | 16 active motors (`mode` 1): four per finger, **index 0–3, middle 4–7, ring 8–11, pinky 12–15** | ✅ (T2, both hands) |
| `motor_state[16..19]` | **The thumb** (4 joints). `mode` 0 and temperature 0, but `q` follows the thumb. So the thumb reports position only, with no temperature or status. | ✅ left hand (T2) / 🟡 right thumb not recorded |
| within a finger | Curling moves the 3rd and 4th slot most (~1.6 and ~1.4 rad, ratio ≈ 0.86 every time, so possibly mechanically coupled); the 1st and 2nd move 0.2–0.8 rad. Which of those is base bend and which is sideways spread isn't known yet. | 🟡 |
| motor `temperature[0]` | **42–66 °C at rest**, which is warm. `[1]` is always 0. | 🟡 |
| `press_sensor_state[0..15]` | 16 pads, 6 of 12 values used per pad. Raw, signed, noisy around 0 (−57…+63 at rest), so it needs zero-offset calibration. Units unknown. | 🟡 |
| pad `temperature`, `lost` | Always 0. `lost` is probably a dropped-packet count. | ❓ / 🟡 |
| `imu_state` | Gyro + accel only (quaternion and rpy are 0). Temperature 6499, probably °C × 100 = 65 °C. | 🟡 |
| `power_v`, `system_v`, `device_v` | ~2.39–2.41 V, all equal. Not a supply voltage. | ❓ |
| `power_a` | 0.018–0.032 | ❓ |
| `error[2]` | 0 | 🟡 bits ❓ |

## Robot tests to settle the unknowns

Run these on the gantry, robot powered, in damping or zero-torque mode so the joints can be moved by hand. Record each one with:

```
python -m h2diag live --iface eth10 --record t1_waist   # type a note + Enter at each action
```

Drop a marker at each action (type what you did + Enter); markers are saved in the recording.

**Tip:** type the marker *before* each movement. It makes the analysis simpler, and the 2026-11-17 recordings had them after.

| # | Action | Settles | Status |
|---|---|---|---|
| T1 | Move one joint at a time by hand: waist yaw, waist roll, waist pitch, then each wrist (roll, pitch, yaw), left then right | Joint order for 12–14, 19–21 and 26–28 | **Mostly done 2026-11-17.** Left: see slot 20/27 move by bending the hand side to side. |
| T2 | Curl each finger of each hand one at a time | Which hand motor slot is which finger joint; what slots 16–19 do | **Done 2026-11-17** except the right thumb. Left: right thumb; separate base bend from spread (fingers 1st/2nd slot). |
| T3 | Record 10 min at rest, then 10 min holding a pose (or walking, if allowed) | Whether `temperature[0]` vs `[1]` behave like winding vs. housing; whether the hot group comes from holding the pose | |
| T4 | Record the battery while idle, then while charging | The sign and units of `current` | |
| T5 | Press each fingertip and palm area firmly | Pad layout and pressure scale | |
| T6 | Switch robot modes with the remote (damping → stand → ...) while recording | `mode_machine`, `mode_pr`, the mode topics (also watch `rt/arm/action/state`, `rt/rtc/state`) | |
| T7 | Short slow walk or squat if safe; otherwise skip | `tau_est` scale and the `lowcmd` vs. `lowstate` relationship | |

**Joints too stiff to move by hand:** use the two-IMU method from T1 (the relative rotation between pelvis and torso IMU) for the waist. Another read-only option is to record while the robot performs one of its own built-in actions from the remote/app. Our software only listens.
