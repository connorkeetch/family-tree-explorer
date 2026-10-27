/**
 * Two-thumb range slider built from two overlaid <input type="range"> elements
 * sharing one track, with a highlighted fill between the thumbs. Replaces the
 * two separate stacked sliders, which could visually cross and read as broken.
 * Each thumb clamps against the other so low ≤ high always holds.
 */
export default function DualRange({
  min,
  max,
  low,
  high,
  onChange,
  lowLabel = "Minimum",
  highLabel = "Maximum",
}: {
  min: number;
  max: number;
  low: number;
  high: number;
  onChange: (low: number, high: number) => void;
  lowLabel?: string;
  highLabel?: string;
}) {
  const pct = (v: number) => (max > min ? ((v - min) / (max - min)) * 100 : 0);

  return (
    <div className="dualrange">
      <div className="dualrange-track" />
      <div
        className="dualrange-fill"
        style={{ left: `${pct(low)}%`, right: `${100 - pct(high)}%` }}
      />
      <input
        type="range"
        min={min}
        max={max}
        value={low}
        aria-label={lowLabel}
        onChange={(e) => onChange(Math.min(+e.target.value, high), high)}
      />
      <input
        type="range"
        min={min}
        max={max}
        value={high}
        aria-label={highLabel}
        onChange={(e) => onChange(low, Math.max(+e.target.value, low))}
      />
    </div>
  );
}
