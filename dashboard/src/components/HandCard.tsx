/**
 * One Dex5 hand: a motor-temperature grid (5 fingers x 4 motors, slot order from T2)
 * and the 16 pressure pads. The thumb reports q only, so its cells show "q" + the value.
 * Pad positions on the hand aren't known yet, so pads are shown in slot order 0-15.
 */
import type { ReactNode } from "react";
import { useBridge } from "../bridge";
import { cssColor, FINGERS, handLevel, handMaxTemp, handMotorLevel, heatColor, motorTemp, padFill, type Side } from "../derive";

export function HandCard({ side }: { side: Side }) {
  const { snap } = useBridge();
  const hand = snap?.hands[side] ?? null;
  const title = side === "left" ? "Left hand" : "Right hand";
  if (!hand) return <div className="card empty">{title} · no data</div>;

  const level = handLevel(snap!.warnings, side);
  const max = handMaxTemp(hand);
  return (
    <div className="card">
      <div className="card-head">
        <span className={`dot ${level ?? "ok"}`} />
        {title}
        <span className="aside">{max !== null ? `max ${max} °C` : ""}</span>
      </div>

      <div className="fingers">
        {FINGERS.map((f) => (
          <FingerRow key={f.name} name={f.name}>
            {f.slots.map((slot) => {
              const m = hand.motors[slot];
              if (!m) return <div key={slot} className="cell inactive">–</div>;
              if (!m.active) {
                return (
                  <div key={slot} className="cell inactive" title={`slot ${slot}: reports position only`}>
                    {m.q === null ? "–" : m.q.toFixed(2)}
                  </div>
                );
              }
              const t = motorTemp(m.temp);
              const lvl = handMotorLevel(snap!.warnings, side, slot);
              return (
                <div key={slot} className="cell" style={{ background: cssColor(heatColor(t, lvl)) }}
                     title={`slot ${slot} · q ${m.q?.toFixed(3) ?? "–"} rad`}>
                  {t ?? "–"}
                </div>
              );
            })}
          </FingerRow>
        ))}
      </div>

      <div className="pads-label">Pressure · raw, uncalibrated</div>
      <div className="pads">
        {hand.pressure.map((_, pad) => {
          const lost = hand.pads_lost[pad] !== 0;
          return (
            <div key={pad} className={`pad${lost ? " lost" : ""}`} title={`pad ${pad}${lost ? " · lost" : ""}`}>
              {!lost && <div className="fill" style={{ opacity: padFill(hand, pad) }} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FingerRow({ name, children }: { name: string; children: ReactNode }) {
  return (
    <>
      <div className="finger-name">{name}</div>
      {children}
    </>
  );
}
