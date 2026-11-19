import { describe, expect, it } from "vitest";
import leftUrdf from "../../public/renders/dex5_hands/Dex5-URDF-L/Dex5-URDF-L.urdf?raw";
import rightUrdf from "../../public/renders/dex5_hands/Dex5-URDF-R/Dex5-URDF-R.urdf?raw";
import { fixture } from "../contract/fixture";
import type { Hand } from "../contract/snapshot";
import { heatColor } from "./heat";
import { dex5Link, drawable, handAngles, handColors } from "./handPose";

/** Child link -> [lower, upper] for every moving joint in a Dex5 URDF. */
function movingLinks(urdf: string): Map<string, [number, number]> {
  const out = new Map<string, [number, number]>();
  for (const j of urdf.matchAll(/<joint[^>]*type="revolute"[\s\S]*?<\/joint>/g)) {
    const child = j[0].match(/<child link="([^"]+)"/)![1];
    const lim = j[0].match(/lower="([^"]+)" upper="([^"]+)"/)!;
    out.set(child, [Number(lim[1]), Number(lim[2])]);
  }
  return out;
}
const LINKS = { left: movingLinks(leftUrdf), right: movingLinks(rightUrdf) };
const hand = (): Hand => structuredClone(fixture.hands.left!);

describe("Dex5 hand slots -> URDF", () => {
  it("puts index, thumb and pinky where the URDF has them", () => {
    expect(dex5Link("left", 0)).toBe("Link_21L"); // index base (roll)
    expect(dex5Link("left", 15)).toBe("Link_54L"); // pinky tip
    expect(dex5Link("right", 16)).toBe("Link_11R"); // thumb base (yaw)
  });

  it("covers all 20 moving joints of each hand, each once", () => {
    for (const side of ["left", "right"] as const) {
      const links = Array.from({ length: 20 }, (_, s) => dex5Link(side, s));
      expect(new Set(links)).toEqual(new Set(LINKS[side].keys()));
    }
  });

  it("matches the T2 ranges: 3rd/4th finger slots top out at the Pitch_x3/x4 limits", () => {
    expect(LINKS.left.get(dex5Link("left", 2))![1]).toBeCloseTo(1.69, 1); // T2 max 1.69
    expect(LINKS.left.get(dex5Link("left", 3))![1]).toBeCloseTo(1.40, 1); // T2 max 1.40
    expect(LINKS.left.get(dex5Link("left", 0))).toEqual([-0.38397, 0.38397]); // signed spread
  });
});

describe("hand pose and colours", () => {
  it("skips missing q and values outside the limits", () => {
    const h = hand();
    h.motors[2].q = null;
    expect(handAngles(h, "left").has("Link_23L")).toBe(false);
    expect(drawable(1.7, 0, 1.684)).toBe(true); // within tolerance
    expect(drawable(2.88, 0, 1.8151)).toBe(false); // right thumb slot 17 in T2
  });

  it("greys the thumb and colours a warned motor amber", () => {
    const colors = handColors(hand(), "left", [{ id: "hand_left:temp:5", level: "warn", subsystem: "hand_left", msg: "" }]);
    expect(colors.get("Link_11L")).toBe(heatColor(null)); // thumb: no temperature
    expect(colors.get("Link_32L")).toBe(heatColor(20, "warn")); // slot 5 = middle, 2nd joint
  });
});
