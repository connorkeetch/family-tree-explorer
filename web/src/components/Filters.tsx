import { AMERICAN, type FilterState } from "../lib/filter";
import type { Ranges } from "../api/types";
import { formatYear } from "../lib/year";
import DualRange from "./DualRange";

export default function Filters({
  filter,
  setFilter,
  countries,
  states,
  ranges,
  onReset,
}: {
  filter: FilterState;
  setFilter: (f: FilterState) => void;
  countries: { name: string; count: number }[];
  states: { name: string; count: number }[];
  ranges: Ranges;
  onReset: () => void;
}) {
  const set = (patch: Partial<FilterState>) => setFilter({ ...filter, ...patch });

  return (
    <div>
      <div className="field">
        <span>Branch</span>
        <div style={{ display: "flex", gap: 6 }}>
          {(["all", "P", "M"] as const).map((b) => (
            <button
              key={b}
              className={filter.branch === b ? "btn-primary" : ""}
              style={{ flex: 1, padding: "6px 0" }}
              onClick={() => set({ branch: b })}
            >
              {b === "all" ? "All" : b === "P" ? "Paternal" : "Maternal"}
            </button>
          ))}
        </div>
      </div>

      {ranges.gen_hi > ranges.gen_lo && (
        <div className="field">
          <span>
            Generations back: {filter.genMin}–{filter.genMax}
            {filter.genMax < ranges.gen_hi ? " (closer in)" : ""}
          </span>
          <DualRange
            min={ranges.gen_lo}
            max={ranges.gen_hi}
            low={filter.genMin}
            high={filter.genMax}
            onChange={(lo, hi) => set({ genMin: lo, genMax: hi })}
            lowLabel="Closest generation"
            highLabel="Furthest generation back"
          />
        </div>
      )}

      <div className="field">
        <span>Country of birth</span>
        <select
          value={filter.country}
          onChange={(e) => {
            const country = e.target.value;
            // Dropping out of the American selection clears any state filter, so it
            // can't silently zero out every other country's ancestors.
            set({ country, ...(country === AMERICAN ? {} : { state: "all" }) });
          }}
        >
          <option value="all">any country</option>
          {countries.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name} · {c.count}
            </option>
          ))}
        </select>
      </div>

      {filter.country === AMERICAN && states.length > 0 && (
        <div className="field">
          <span>State of birth</span>
          <select value={filter.state} onChange={(e) => set({ state: e.target.value })}>
            <option value="all">any state</option>
            {states.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name} · {s.count}
              </option>
            ))}
          </select>
        </div>
      )}

      <div style={{ display: "flex", gap: 10 }}>
        <div className="field" style={{ flex: 1 }}>
          <span>Sex</span>
          <select value={filter.sex} onChange={(e) => set({ sex: e.target.value as FilterState["sex"] })}>
            <option value="all">any</option>
            <option value="M">male</option>
            <option value="F">female</option>
          </select>
        </div>
        <div className="field" style={{ flex: 1 }}>
          <span>DNA line</span>
          <select value={filter.dna} onChange={(e) => set({ dna: e.target.value as FilterState["dna"] })}>
            <option value="all">any</option>
            <option value="Y">Y (patrilineal)</option>
            <option value="mt">mt (matrilineal)</option>
          </select>
        </div>
      </div>

      {ranges.has_years && (
        <div className="field">
          <span>
            Birth year: {formatYear(filter.yrMin)}–{formatYear(filter.yrMax)}
          </span>
          <DualRange
            min={ranges.yr_lo}
            max={ranges.yr_hi}
            low={filter.yrMin}
            high={filter.yrMax}
            onChange={(lo, hi) => set({ yrMin: lo, yrMax: hi })}
            lowLabel="Earliest birth year"
            highLabel="Latest birth year"
          />
        </div>
      )}

      <button onClick={onReset} style={{ marginTop: 4 }}>
        Reset filters
      </button>
    </div>
  );
}
