/**
 * A real bridge message, typed. The assignment below is the contract check:
 * if snapshot.ts and the bridge disagree, `npm run typecheck` fails here.
 * Also handy as test data and as a stand-in before the bridge connects.
 * Regenerate: see bridge/tests/test_contract.py.
 */
import raw from "./snapshot.fixture.json";
import type { Snapshot } from "./snapshot";

// JSON imports widen "snapshot" to string, so pin the literal fields first.
export const fixture: Snapshot = {
  ...raw,
  type: "snapshot",
  source: raw.source === "live" ? "live" : "replay",
  support_raw: {
    ...raw.support_raw,
    state: raw.support_raw.state === "ground" || raw.support_raw.state === "gantry" ? raw.support_raw.state : null,
  },
  warnings: raw.warnings.map((w) => ({
    ...w,
    level: w.level === "error" || w.level === "warn" ? w.level : "info",
  })),
};
