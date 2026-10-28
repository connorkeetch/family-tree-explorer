/** Separate native sliders keep both ends reachable by touch and keyboard. */
export default function DualRange({ min, max, low, high, onChange, lowLabel = "Minimum", highLabel = "Maximum" }: {
  min: number; max: number; low: number; high: number;
  onChange: (low: number, high: number) => void; lowLabel?: string; highLabel?: string;
}) {
  return <div className="range-pair">
    {[{ label: lowLabel, value: low, lower: true }, { label: highLabel, value: high, lower: false }].map(({ label, value, lower }) => {
      const update = (n: number) => {
        const valid = Math.max(min, Math.min(max, Math.round(n)));
        onChange(lower ? Math.min(valid, high) : low, lower ? high : Math.max(valid, low));
      };
      return <div className="range-bound" key={label}>
        <label><span>{label}</span><input type="number" key={value} defaultValue={value} min={lower ? min : low}
          max={lower ? high : max} aria-label={`${label} value`}
          onBlur={(e) => { const n = e.target.value.trim() ? Number(e.target.value) : NaN;
            if (Number.isFinite(n)) update(n); e.target.value = String(Number.isFinite(n) ? Math.max(lower ? min : low, Math.min(lower ? high : max, Math.round(n))) : value); }}
          onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} /></label>
        <input type="range" min={min} max={max} value={value} aria-label={label} onChange={(e) => update(+e.target.value)} />
      </div>;
    })}
  </div>;
}
