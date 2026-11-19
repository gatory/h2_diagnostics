/**
 * The bridge <-> dashboard contract: every message on ws://<thor>:8765.
 *
 * Mirrors bridge/h2_diagnostics/processing/state.py (the snapshot) and
 * output/server.py (acks + commands). Kept honest from both sides:
 *   - fixture.ts assigns a real message (snapshot.fixture.json) to `Snapshot`,
 *     so `npm run typecheck` fails if these types drift from the bridge;
 *   - bridge/tests/test_contract.py fails if the bridge's output drifts from the fixture.
 *
 * Fields ending in `_raw` have unconfirmed meaning (docs/field_map.md):
 * show them with a "?", never colour or warn on them.
 * `null` means "no message for that topic yet" (or, for numbers, not measurable yet).
 */

// ---- Server -> app -------------------------------------------------------------

export interface Snapshot {
  type: "snapshot";
  t: number; // the bridge's clock (time.time()) when built, even during replay (NOT the recording's time)
  source: "live" | "replay";
  joint_order_verified: boolean; // false until slots 20/27 are seen moving
  topics: Record<string, TopicReport>;
  body: Body | null;
  imu: { pelvis: Imu | null; torso: Imu | null };
  mode: Mode;
  battery: Battery | null;
  mainboard: Mainboard | null;
  hands: { left: Hand | null; right: Hand | null };
  support_raw: SupportRaw; // ground or gantry, from knee torque: UNCONFIRMED, display only
  warnings: Warning[]; // from the bridge's HealthMonitor; the dashboard never invents its own
  recorder?: RecorderStatus; // absent when the bridge runs without a recorder
}

/**
 * The bridge's guess whether the robot stands on the ground (processing/support.py):
 * summed |knee tau| with hysteresis. Thresholds are provisional (no ground recording yet).
 */
export interface SupportRaw {
  state: "ground" | "gantry" | null; // null: no body data / invalid torque
  knee_load_nm: number | null;
}

export interface TopicReport {
  hz: number | null; // measured receive rate (null until watched 0.5 s)
  age_s: number | null; // seconds since the last message
  count: number;
  expected_hz: number | null; // from layout.LIVE_TOPICS; null for other topics
}

/** One motor. Body joints and hand motors share this shape. */
export interface Motor {
  i: number; // slot index
  q: number | null; // position, rad (null = invalid number from the robot)
  dq: number | null; // velocity, rad/s
  tau: number | null; // estimated torque, N·m
  temp: number[]; // [two sensors], °C
  vol: number | null;
  mode: number;
  motorstate: number; // error bits, 0 = ok
}

export interface Joint extends Motor {
  name: string; // layout.JOINTS name, e.g. "L_knee" (URDF: "left_knee_joint")
}

export interface Body {
  joints: Joint[]; // 31, slot order
  mode_machine: number;
  mode_pr: number; // 0 = PR (angles, drive the 3D view); 1 = AB (raw motor A/B, not angles!)
  tick: number;
  spare_slots_active: boolean;
}

export interface Imu {
  quat: number[]; // [w, x, y, z]
  gyro: number[]; // rad/s
  accel: number[]; // m/s²
  rpy: number[]; // rad
  temp_raw: number;
}

export interface Mode {
  fsm_id_raw: number | null; // null until test T6 confirms the source
  fsm_name_raw: string | null;
}

export interface Battery {
  soc: number; // %
  soh: number; // %
  voltage: number; // V
  current_raw: number; // probably mA, negative = discharge (unconfirmed)
  cells: number[]; // 18, V
  cell_spread_mv: number | null;
  temps: number[];
  cycles: number;
  state_raw: number[];
}

export interface Mainboard {
  temps: number[];
  fans: number[];
  state: number[];
}

export interface HandMotor extends Motor {
  active: boolean; // false for the thumb slots 16-19 (they report q only)
}

export interface Hand {
  motors: HandMotor[]; // 20: index 0-3, middle 4-7, ring 8-11, pinky 12-15, thumb 16-19
  pressure: number[][]; // 16 pads x 6 raw values (uncalibrated)
  pads_lost: number[];
  gyro: number[];
  accel: number[];
  imu_temp_raw: number;
  error: number[];
  power_v_raw: number;
  power_a_raw: number;
}
export type WarningLevel = "error" | "warn" | "info";

export interface Warning {
  id: string; // stable, e.g. "temp:R_knee"
  level: WarningLevel;
  subsystem: string;
  msg: string;
}

export type RecorderStatus =
  | { recording: false }
  | { recording: true; name: string; file: string; elapsed_s: number };

export interface Ack {
  type: "ack";
  cmd: string | null;
  ok: boolean;
  file?: string | null;
  error?: string;
}

export type ServerMessage = Snapshot | Ack;

// ---- App -> server (recorder only; nothing reaches the robot) --------------------

export type Command =
  | { cmd: "record_start"; name: string; notes?: string }
  | { cmd: "record_stop" }
  | { cmd: "marker"; text: string };
