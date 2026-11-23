/**
 * What the bridge sends over ws://<host>:8765 (bridge/README.md, "WebSocket protocol").
 * Mirrors bridge/h2_diagnostics/processing/state.py on main. Fields ending in `_raw`
 * have an unconfirmed meaning: show them with a "?", never colour or warn on them.
 * `null` = no message for that topic yet.
 */

export interface Snapshot {
  type: "snapshot";
  t: number; // bridge clock (unix seconds) when built; NOT the recording's time in replay
  source: "live" | "replay";
  joint_order_verified: boolean;
  topics: Record<string, TopicReport>;
  body: Body | null;
  imu: { pelvis: Imu | null; torso: Imu | null };
  mode: { fsm_id_raw: number | null; fsm_name_raw: string | null };
  battery: Battery | null;
  mainboard: Mainboard | null;
  hands: { left: Hand | null; right: Hand | null };
  warnings: Warning[]; // from the bridge's health checks, most severe first
  recorder?: RecorderStatus; // only when the bridge runs with a recorder (`serve`)
}

export interface TopicReport {
  hz: number | null; // null until watched for 0.5 s
  age_s: number | null;
  count: number;
}

export interface Motor {
  i: number; // slot
  q: number | null; // rad
  dq: number | null;
  tau: number | null; // N·m
  temp: number[]; // two sensors, °C (0 = no sensor)
  vol: number | null;
  mode: number;
  motorstate: number; // error bits, 0 = ok
}

export interface Joint extends Motor {
  name: string; // e.g. "L_knee" (bridge/h2_diagnostics/layout.py)
}

export interface Body {
  joints: Joint[]; // 31, in slot order
  mode_machine: number;
  mode_pr: number; // 0 = PR (angles); 1 = AB (raw motor positions, NOT angles)
  tick: number;
  spare_slots_active: boolean;
}

export interface Imu {
  quat: number[];
  gyro: number[];
  accel: number[];
  rpy: number[]; // rad
  temp_raw: number;
}

export interface Battery {
  soc: number; // %
  soh: number;
  voltage: number; // V
  current_raw: number; // probably mA, negative = discharge (unconfirmed)
  cells: number[];
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
  active: boolean; // false for the thumb (slots 16-19 report q only)
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

export type Level = "error" | "warn" | "info";

export interface Warning {
  id: string; // stable, e.g. "temp:R_knee", "hand_left:temp:3", "stale:rt/lf/bmsstate"
  level: Level;
  subsystem: string;
  msg: string;
}

export interface RecorderStatus {
  recording: boolean;
  name?: string;
  file?: string;
  elapsed_s?: number;
}

// ---- app -> bridge (recorder only; nothing reaches the robot) ----

export type Command =
  | { cmd: "record_start"; name: string; notes?: string }
  | { cmd: "record_stop" }
  | { cmd: "marker"; text: string };

export interface Ack {
  type: "ack";
  cmd: string | null;
  ok: boolean;
  file?: string | null;
  error?: string;
}
