export interface BarItem {
  name: string;
  value: number; // percentage 0-100, or a raw count if `asCount`
  color: string;
  count?: number;
}

// A nonzero share that rounds to "0.0%" reads as a bug next to its raw count, so
// floor it to "<0.1%" (the count still tells the exact story).
const fmtPct = (v: number) => (v > 0 && v < 0.05 ? "<0.1%" : `${v.toFixed(1)}%`);

export default function OriginBars({
  items,
  asCount = false,
  max,
}: {
  items: BarItem[];
  asCount?: boolean;
  max?: number;
}) {
  if (!items.length) return <div className="sub">no data</div>;
  const top = max ?? Math.max(...items.map((i) => i.value), 1);
  return (
    <div>
      {items.map((it) => (
        <div className="row" key={it.name}>
          <span className="sw" style={{ background: it.color }} />
          <span className="lbl">{it.name}</span>
          <span className="track">
            <span
              className="fill"
              style={{ width: `${(100 * it.value) / top}%`, background: it.color }}
            />
          </span>
          <span className="pct">
            {asCount ? it.value.toLocaleString() : fmtPct(it.value)}
            {it.count != null && <span className="cnt"> ({it.count.toLocaleString()})</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
