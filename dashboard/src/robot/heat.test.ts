import { describe, expect, it } from "vitest";
import { fixture } from "../contract/fixture";
import { findJoint, heatColor, jointColors, jointTemp, tempWarnings } from "./heat";

describe("heat colours", () => {
  it("uses the hotter sensor and treats 0 as no sensor", () => {
    expect(jointTemp([41, 48])).toBe(48);
    expect(jointTemp([66, 0])).toBe(66);
    expect(jointTemp([0, 0])).toBeNull();
  });

  it("is a gradient below any warning, clamped at both ends", () => {
    expect(heatColor(20)).toBe(heatColor(30));
    expect(heatColor(90)).toBe(heatColor(65));
    expect(heatColor(45)).not.toBe(heatColor(30));
    expect(heatColor(null)).not.toBe(heatColor(30)); // "unknown" looks different from "cool"
  });

  it("goes amber/red only on the bridge's word, whatever the number", () => {
    expect(heatColor(40, "warn")).toBe(heatColor(99, "warn"));
    expect(heatColor(40, "error")).not.toBe(heatColor(40, "warn"));
    expect(heatColor(99, "info")).toBe(heatColor(99)); // info is not a colour
  });

  it("reads temperature warnings from the fixture (R_knee at 72 °C -> warn)", () => {
    expect(tempWarnings(fixture.warnings).get("R_knee")).toBe("warn");
    const colors = jointColors(fixture);
    expect(colors.size).toBe(31);
    expect(colors.get("right_knee_joint")).toBe(heatColor(0, "warn"));
    expect(colors.get("left_knee_joint")).not.toBe(colors.get("right_knee_joint"));
  });

  it("finds the clicked joint by URDF name", () => {
    expect(findJoint(fixture, "left_knee_joint")?.i).toBe(3);
    expect(findJoint(fixture, "camera")).toBeUndefined();
    expect(findJoint(null, "left_knee_joint")).toBeUndefined();
  });
});
