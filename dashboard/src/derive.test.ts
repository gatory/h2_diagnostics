import { describe, expect, it } from "vitest";
import {
  COLOR, heatColor, hottestJoint, jointAngles, jointColors, jointLevel, handMotorLevel, motorTemp,
  topicLabel, urdfJointName, verdict, verdictText, worst,
} from "./derive";
import type { Body, Joint, Snapshot, Warning } from "./types";

const joint = (name: string, i: number, temp: number[], q = 0.1): Joint =>
  ({ i, name, q, dq: 0, tau: 0, temp, vol: 0, mode: 1, motorstate: 0 });
const body = (joints: Joint[], mode_pr = 0): Body =>
  ({ joints, mode_machine: 1, mode_pr, tick: 0, spare_slots_active: false });
const w = (id: string, level: Warning["level"]): Warning => ({ id, level, subsystem: "x", msg: id });
const snap = (warnings: Warning[], b: Body | null = null): Snapshot => ({
  type: "snapshot", t: 0, source: "replay", joint_order_verified: false, topics: {}, body: b,
  imu: { pelvis: null, torso: null }, mode: { fsm_id_raw: null, fsm_name_raw: null },
  battery: null, mainboard: null, hands: { left: null, right: null }, warnings,
});

describe("status comes only from the bridge's warnings", () => {
  it("verdict is the worst level; info doesn't count", () => {
    expect(verdict(null)).toBe("nodata");
    expect(verdict(snap([w("spare_slots", "info")]))).toBe("ok");
    expect(verdict(snap([w("temp:L_knee", "warn")]))).toBe("warn");
    expect(verdict(snap([w("temp:L_knee", "warn"), w("missing:body", "error")]))).toBe("fault");
  });

  it("verdict text counts faults and warnings", () => {
    expect(verdictText(snap([]))).toBe("All systems normal");
    expect(verdictText(snap([w("a", "error"), w("b", "warn"), w("c", "warn")]))).toBe("1 fault · 2 warnings");
  });

  it("worst respects the id filter", () => {
    expect(worst([w("soc", "warn"), w("missing:body", "error")], (id) => id === "soc")).toBe("warn");
  });
});

describe("joints", () => {
  it("maps names to the URDF, never by order", () => {
    expect(urdfJointName("L_knee")).toBe("left_knee_joint");
    expect(urdfJointName("R_wrist_yaw")).toBe("right_wrist_yaw_joint");
    expect(urdfJointName("waist_yaw")).toBe("waist_yaw_joint");
  });

  it("a joint's level comes from any warning about it, not about a hand or another joint", () => {
    const ws = [w("limit:L_knee", "warn"), w("temp:R_knee", "error"), w("hand_left:temp:3", "error")];
    expect(jointLevel(ws, "L_knee")).toBe("warn");
    expect(jointLevel(ws, "R_knee")).toBe("error");
    expect(jointLevel(ws, "waist_yaw")).toBeNull();
  });

  it("hottest ignores sensors that read 0", () => {
    expect(motorTemp([0, 0])).toBeNull();
    const hot = hottestJoint(body([joint("L_knee", 3, [40, 0]), joint("waist_yaw", 12, [0, 53])]));
    expect(hot?.joint.name).toBe("waist_yaw");
    expect(hot?.temp).toBe(53);
  });

  it("freezes the pose when linkage slots aren't angles (mode_pr 1)", () => {
    expect(jointAngles(body([joint("L_knee", 3, [30])], 1))).toBeNull();
    expect(jointAngles(body([joint("L_knee", 3, [30], 0.4)]))).toEqual({ left_knee_joint: 0.4 });
  });

  it("colours: gradient for warmth, amber/red only from warnings", () => {
    expect(heatColor(20)).toBe(COLOR.cool);
    expect(heatColor(80)).toBe(COLOR.warm); // hot but no warning: still just "warm"
    expect(heatColor(80, "error")).toBe(COLOR.error);
    expect(heatColor(null)).toBe(COLOR.nodata);
    const colors = jointColors(snap([w("temp:L_knee", "warn")], body([joint("L_knee", 3, [72])])));
    expect(colors.get("left_knee_joint")).toBe(COLOR.warn);
  });
});

describe("hands and topics", () => {
  it("hand motor level matches only that side and slot", () => {
    const ws = [w("hand_left:temp:3", "warn"), w("hand_left:temp:13", "error")];
    expect(handMotorLevel(ws, "left", 3)).toBe("warn");
    expect(handMotorLevel(ws, "left", 1)).toBeNull(); // "13" must not match slot 1 or 3
    expect(handMotorLevel(ws, "right", 3)).toBeNull();
  });

  it("topic labels", () => {
    expect(topicLabel("rt/lf/lowstate")).toBe("Body");
    expect(topicLabel("rt/lowstate")).toBe("Body");
    expect(topicLabel("rt/dex5/right/state")).toBe("Right hand");
  });
});
