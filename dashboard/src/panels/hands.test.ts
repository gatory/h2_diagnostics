import { describe, expect, it } from "vitest";
import { fixture } from "../contract/fixture";
import type { Warning } from "../contract/snapshot";
import { FINGERS, handLevel, motorLevels, padTiles, PRESSURE_FULL_RAW } from "./hands";

const w = (id: string, level: Warning["level"]): Warning => ({ id, level, subsystem: "x", msg: id });

describe("hand panel logic", () => {
  it("covers all 20 slots once, thumb last (T2 layout)", () => {
    const slots = FINGERS.flatMap((f) => f.slots);
    expect(slots).toEqual([...Array(20).keys()]);
    expect(FINGERS[4]).toEqual({ name: "thumb", slots: [16, 17, 18, 19] });
    // the bridge marks exactly the thumb inactive
    const inactive = fixture.hands.left!.motors.filter((m) => !m.active).map((m) => m.i);
    expect(inactive).toEqual(FINGERS[4].slots);
  });

  it("keeps the two hands' warnings apart", () => {
    const ws = [w("hand_left:temp:5", "warn"), w("hand_right:motorstate:2", "error"), w("temp:L_knee", "error")];
    expect(handLevel(ws, "left")).toBe("warn");
    expect(handLevel(ws, "right")).toBe("error");
    expect(handLevel([w("missing:hand_right", "error")], "right")).toBe("error");
    expect(handLevel([w("temp:L_knee", "error")], "left")).toBeNull();
  });

  it("maps warnings to motor slots, error beating warn", () => {
    const levels = motorLevels([w("hand_left:temp:5", "warn"), w("hand_left:motorstate:5", "error"),
                                w("hand_left:temp:12", "warn"), w("hand_left:pads_lost", "warn")], "left");
    expect(levels.get(5)).toBe("error");
    expect(levels.get(12)).toBe("warn");
    expect(levels.size).toBe(2);
  });

  it("turns raw pressure into dim tiles at rest", () => {
    const tiles = padTiles(fixture.hands.left!);
    expect(tiles).toHaveLength(16);
    expect(tiles.every((t) => t.fill < 0.2)).toBe(true); // resting noise stays dim
    const pressed = { ...fixture.hands.left!, pressure: fixture.hands.left!.pressure.map((c, i) => (i === 3 ? c.map(() => -900) : c)) };
    expect(padTiles(pressed)[3]).toMatchObject({ peak: 900, fill: 1 });
    expect(PRESSURE_FULL_RAW).toBeGreaterThan(63 * 3);
  });
});
