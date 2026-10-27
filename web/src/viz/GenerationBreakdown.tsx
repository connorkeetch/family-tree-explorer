import type { GenComposition } from "../lib/insights";

// "You" for the root, then "Gen 1" (parents), "Gen 2" (grandparents), ...
const genLabel = (g: number) => (g === 0 ? "You" : `Gen ${g}`);

// Whole numbers read best for the big shares the user cares about (75% / 25%);
// keep one decimal in the single-digit range, and floor tiny slivers to "<1%"
// (their raw count is still shown in the chip, so nothing is hidden).
const fmtPct = (p: number) =>
  p >= 9.95 ? `${Math.round(p)}%` : p >= 0.95 ? `${Math.round(p * 10) / 10}%` : "<1%";

// Per-generation ancestry composition — the textual companion to the fan's rings.
// One stacked bar per generation (each segment = an origin's share of the 2ⁿ
// slots) plus readable %/count chips. Data comes from deriveGenComposition.
export default function GenerationBreakdown({ data }: { data: GenComposition[] }) {
  if (!data.length) return null;
  return (
    <div className="genbreak">
      {data.map((row) => (
        <div className="genbreak-row" key={row.gen}>
          <div className="genbreak-head">
            <span className="genbreak-lbl">{genLabel(row.gen)}</span>
            <span className="genbreak-slots">
              {row.known.toLocaleString()}/{row.slots.toLocaleString()} known
            </span>
          </div>
          <div
            className="genbreak-bar"
            role="img"
            aria-label={row.segments.map((s) => `${s.name} ${fmtPct(s.pct)}`).join(", ")}
          >
            {row.segments.map((s, i) => (
              <span
                key={s.name + i}
                style={{ width: `${s.pct}%`, background: s.color }}
                title={`${s.name}: ${fmtPct(s.pct)} · ${s.count.toLocaleString()}`}
              />
            ))}
          </div>
          <div className="genbreak-chips">
            {row.segments.map((s, i) => (
              <span className="genbreak-chip" key={s.name + i}>
                <span className="sw" style={{ background: s.color }} />
                {s.name} <b>{fmtPct(s.pct)}</b>
                <span className="cnt"> ({s.count.toLocaleString()})</span>
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
