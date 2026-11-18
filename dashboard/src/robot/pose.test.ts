import { describe, expect, it } from "vitest";
import h2Urdf from "../../public/renders/h2_description/H2.urdf?raw";
import { fixture } from "../contract/fixture";
import type { Snapshot } from "../contract/snapshot";
import { urdfJointName } from "./jointMap";
import { poseFromSnapshot } from "./pose";

const movingUrdfJoints = new Set(
  // strip <!-- comments --> first: H2.urdf has a commented-out floating_base_joint
  [...h2Urdf.replace(/<!--[\s\S]*?-->/g, "").matchAll(/<joint\s+name="([^"]+)"\s+type="(\w+)"/g)]
    .filter((m) => m[2] !== "fixed")
    .map((m) => m[1]),
);
const withBody = (patch: Partial<NonNullable<Snapshot["body"]>>): Snapshot => ({
  ...fixture,
  body: { ...fixture.body!, ...patch },
});

describe("joint names", () => {
  it("maps the bridge's style to the URDF's", () => {
    expect(urdfJointName("L_knee")).toBe("left_knee_joint");
    expect(urdfJointName("R_wrist_yaw")).toBe("right_wrist_yaw_joint");
    expect(urdfJointName("waist_yaw")).toBe("waist_yaw_joint");
  });

  it("finds every snapshot joint in H2.urdf, and nothing extra", () => {
    const mapped = fixture.body!.joints.map((j) => urdfJointName(j.name));
    expect(mapped.filter((n) => !movingUrdfJoints.has(n))).toEqual([]);
    expect(new Set(mapped)).toEqual(movingUrdfJoints);
  });
});

describe("poseFromSnapshot", () => {
  it("sets all 31 joints by URDF name from q", () => {
    const pose = poseFromSnapshot(fixture);
    expect(pose.frozen).toBeNull();
    expect(Object.keys(pose.joints)).toHaveLength(31);
    expect(pose.joints["left_knee_joint"]).toBe(fixture.body!.joints[3].q);
  });

  it("takes roll and pitch from the pelvis IMU, never yaw", () => {
    const [roll, pitch] = fixture.imu.pelvis!.rpy;
    expect(poseFromSnapshot(fixture).tilt).toEqual([roll, pitch]);
  });

  it("freezes in AB mode: those slots are motor positions, not angles", () => {
    const pose = poseFromSnapshot(withBody({ mode_pr: 1 }));
    expect(pose.frozen).toMatch(/AB/);
    expect(pose.joints).toEqual({});
  });

  it("skips a joint whose q is invalid instead of drawing it at 0", () => {
    const joints = fixture.body!.joints.map((j) => (j.i === 3 ? { ...j, q: null } : j));
    const pose = poseFromSnapshot(withBody({ joints }));
    expect(pose.joints).not.toHaveProperty("left_knee_joint");
    expect(Object.keys(pose.joints)).toHaveLength(30);
  });

  it("waits for data", () => {
    expect(poseFromSnapshot({ ...fixture, body: null }).frozen).toMatch(/no body/);
    expect(poseFromSnapshot({ ...fixture, imu: { pelvis: null, torso: null } }).tilt).toBeNull();
  });
});
