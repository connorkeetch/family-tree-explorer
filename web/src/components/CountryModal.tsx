import { useRef } from "react";
import type { Colors, CountryDatum, CountryDetail } from "../api/types";
import { useFocusTrap } from "../lib/useFocusTrap";
import { formatYear } from "../lib/year";
import OriginBars, { BarItem } from "../viz/OriginBars";

function trunc(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/**
 * In-depth detail for a single country, opened by clicking its polygon on the
 * map. Shows every ancestor born there (unfiltered): nationality split, span of
 * known births, by-generation counts, immigrant settlements, family side, top
 * surnames and birthplaces. Empty sections are hidden. Closes on backdrop click,
 * the ✕ button, or Escape.
 */
export default function CountryModal({
  iso,
  name,
  detail,
  datum,
  colors,
  onClose,
}: {
  iso: string;
  name: string;
  detail: CountryDetail;
  datum: CountryDatum | undefined;
  colors: Colors;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, onClose);

  const primary = colors[detail.nats[0]?.[0]] || "#fc4e2a";
  const tally = (rows: [string, number][], color: string, truncTo?: number): BarItem[] =>
    rows.map(([label, count]) => ({
      name: truncTo ? trunc(label, truncTo) : label,
      value: count,
      color,
    }));

  const ancestor = (label: string, a: NonNullable<CountryDetail["earliest"]>) => (
    <div className="row">
      <span className="lbl" style={{ width: "auto", flex: 1 }}>
        {label}: <b>{a.name}</b>
        <span className="cnt"> · {a.place ? trunc(a.place, 40) : "place unknown"}</span>
      </span>
      <span className="pct" style={{ width: "auto", color: "var(--muted)" }}>
        b. {formatYear(a.year)} · gen {a.gen ?? "?"}
      </span>
    </div>
  );

  const branchRows: [string, number][] = (
    [["Paternal", detail.branch.P], ["Maternal", detail.branch.M]] as [string, number][]
  ).filter(([, n]) => n > 0);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${name} detail`}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="modal-close" aria-label="Close" onClick={onClose}>
          ×
        </button>
        <h2 className="modal-title">{name}</h2>
        <div className="modal-nats">
          {detail.nats.map(([n, c], i) => (
            <span key={n}>
              {i > 0 ? " · " : ""}
              {n} <span className="cnt">({c.toLocaleString()})</span>
            </span>
          ))}
        </div>
        <div className="sub">All direct-line ancestors born here — independent of the filters on the left.</div>

        <div className="kpis">
          <div className="kpi">
            <b>{detail.total.toLocaleString()}</b>
            <span>ancestors born here</span>
          </div>
          <div className="kpi">
            <b>{(datum?.immw ?? 0).toFixed(1)}%</b>
            <span>of your immigrant origin</span>
          </div>
          {detail.imm > 0 && (
            <div className="kpi">
              <b>{detail.imm.toLocaleString()}</b>
              <span>immigrants left from here</span>
            </div>
          )}
          {detail.median_life != null && (
            <div className="kpi">
              <b>{Math.round(detail.median_life)} yrs</b>
              <span>median lifespan (n={detail.life_n})</span>
            </div>
          )}
        </div>

        {(detail.earliest || detail.latest) && (
          <>
            <h2 className="modal-sec">Span of known births</h2>
            {detail.earliest && ancestor("Earliest", detail.earliest)}
            {detail.latest && ancestor("Latest", detail.latest)}
          </>
        )}

        {detail.by_gen.length > 0 && (
          <>
            <h2 className="modal-sec">Ancestors by generation</h2>
            <OriginBars items={tally(detail.by_gen.map(([g, c]) => [`gen ${g}`, c]), "#4363d8")} asCount />
          </>
        )}

        {detail.imm > 0 && detail.settle.length > 0 && (
          <>
            <h2 className="modal-sec">
              Where the {detail.imm.toLocaleString()} immigrants
              {detail.imm_span ? ` born ${detail.imm_span[0]}–${detail.imm_span[1]}` : ""} settled
            </h2>
            <OriginBars items={tally(detail.settle, "#8a93a6")} asCount />
          </>
        )}

        {branchRows.length > 0 && (
          <>
            <h2 className="modal-sec">Family side</h2>
            <OriginBars items={tally(branchRows, primary)} asCount />
          </>
        )}

        {detail.surnames.length > 0 && (
          <>
            <h2 className="modal-sec">Top surnames</h2>
            <OriginBars items={tally(detail.surnames, primary)} asCount />
          </>
        )}

        {detail.places.length > 0 && (
          <>
            <h2 className="modal-sec">Top birthplaces</h2>
            <OriginBars items={tally(detail.places, primary, 34)} asCount />
          </>
        )}
      </div>
    </div>
  );
}
