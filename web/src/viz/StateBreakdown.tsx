// Ranked "by U.S. state" breakdown of American-born ancestors (count + % of the
// American selection). Each bar is a toggle on the shared `state` filter: click
// to narrow every view to that state, click the active one again to clear.
//
// The rows are derived upstream from the people set filtered by everything
// EXCEPT state, so all states stay visible and clickable after a pick (the
// dropdown in Filters is the equivalent control). The % denominator is the full
// American direct-ancestor count, and the unmatched remainder is surfaced as an
// explicit "no resolved state" line rather than hidden — same honesty as the
// untraced buckets elsewhere.

export interface StateRow {
  name: string;
  count: number;
  pct: number; // 0–100, out of the full American total (including unknown-state)
}

export default function StateBreakdown({
  rows,
  unknown,
  total,
  selected,
  color,
  onSelect,
}: {
  rows: StateRow[];
  unknown: number;
  total: number;
  selected: string; // "all" or a state name
  color: string;
  onSelect: (state: string) => void;
}) {
  if (!total) return <div className="sub">no U.S.-born ancestors in this selection</div>;
  const max = Math.max(...rows.map((r) => r.count), 1);
  return (
    <div>
      {rows.map((r) => {
        const active = selected === r.name;
        return (
          <button
            type="button"
            key={r.name}
            className={`row rowclick${active ? " row-active" : ""}`}
            style={{ width: "100%", textAlign: "left" }}
            aria-pressed={active}
            onClick={() => onSelect(active ? "all" : r.name)}
            title={active ? `Clear the ${r.name} filter` : `Filter ancestors to ${r.name}`}
          >
            <span className="lbl">{r.name}</span>
            <span className="track">
              <span className="fill" style={{ width: `${(100 * r.count) / max}%`, background: color }} />
            </span>
            <span className="pct">
              {r.count.toLocaleString()} · {r.pct.toFixed(0)}%
            </span>
          </button>
        );
      })}
      {unknown > 0 && (
        <div className="sub" style={{ marginTop: 6 }}>
          + {unknown.toLocaleString()} with no resolved state ({((100 * unknown) / total).toFixed(0)}%)
        </div>
      )}
    </div>
  );
}
