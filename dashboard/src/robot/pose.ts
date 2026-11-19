/**
 * Snapshot -> what the 3D robot should look like. Pure (no three.js), so the rules
 * are unit-tested; RobotScene only applies the result.
 */
import type { Snapshot } from "../contract/snapshot";
import { urdfJointName } from "./jointMap";

export interface Pose {
  /** URDF joint name -> angle (rad). Joints with an invalid q are left out. */
  joints: Record<string, number>;
  /**
   * Pelvis tilt: [roll, pitch] in rad, from the pelvis IMU, or null if unknown.
   * Yaw is dropped on purpose: IMU yaw drifts and has no fixed reference, and the
   * robot should keep facing the camera.
   */
  tilt: [number, number] | null;
  /** Why the joint angles can't be trusted for drawing (null = fine). */
  frozen: string | null;
}

export function poseFromSnapshot(snap: Snapshot): Pose {
  const rpy = snap.imu.pelvis?.rpy;
  const tilt: [number, number] | null = rpy ? [rpy[0], rpy[1]] : null;
  const body = snap.body;
  if (!body) return { joints: {}, tilt, frozen: "no body data yet" };
  // mode_pr 1 (AB): ankle/waist slots hold raw motor A/B positions, not angles.
  if (body.mode_pr !== 0) return { joints: {}, tilt, frozen: `mode_pr ${body.mode_pr} (AB): slots are not angles` };
  const joints: Record<string, number> = {};
  for (const j of body.joints) {
    if (j.q !== null && Number.isFinite(j.q)) joints[urdfJointName(j.name)] = j.q;
  }
  return { joints, tilt, frozen: null };
}

/**
 * What stays still on screen:
 *  - "ground": the floor. The lowest foot is put on the grid, so the pelvis moves
 *    up and down as the legs bend (a standing robot crouches toward the floor).
 *  - "gantry": the pelvis, at standing height. The legs hang and move below it.
 * "auto" follows the bridge's support_raw estimate (unconfirmed), and falls back to
 * "gantry" while unknown, which is the safe picture: nothing is pinned to a floor it may not touch.
 */
export type FrameChoice = "auto" | "ground" | "gantry";
export type Frame = "ground" | "gantry";

export function resolveFrame(snap: Snapshot | null, choice: FrameChoice): Frame {
  if (choice !== "auto") return choice;
  return snap?.support_raw?.state ?? "gantry";
}
