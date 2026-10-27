import { useState } from "react";
import type { OriginEstimate } from "../api/types";

/**
 * The reconciled origin verdict for one ancestor (place + surname + relatives
 * combined). A single amber estimate badge -- kept dashed/amber even when
 * corroborated, so it never reads as a documented FamilySearch fact -- with a ✓
 * when independent signals agree. Click to expand the "why": each contributing
 * signal with its basis and confidence. Renders nothing when there's no usable
 * estimate. Shared by the dead-ends card and the fan chart.
 */
export default function CombinedGuess({ est }: { est: OriginEstimate }) {
  const [open, setOpen] = useState(false);
  if (!est || est.confidence === "none") return null;
  return (
    <span className="combined-guess">
      <button
        type="button"
        className={`guess-badge as-button${est.agreement ? " agree" : ""}`}
        title={est.agreement ? "Independent signals agree — click to see why" : "Estimate — click to see why"}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        ≈ {est.label}
        <span className="conf">{est.confidence}</span>
        {est.agreement && (
          <span className="agree-mark" aria-hidden>
            ✓
          </span>
        )}
      </button>
      {open && (
        <span className="guess-why">
          {est.rationale.map((s, i) => (
            <span className="guess-why-row" key={i}>
              <span className="basis">{s.basis}</span>
              <span className="guess-why-text">
                {s.label} <span className="conf">[{s.confidence}]</span> — {s.why}
              </span>
            </span>
          ))}
        </span>
      )}
    </span>
  );
}
