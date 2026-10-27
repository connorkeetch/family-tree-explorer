import { useEffect, useMemo, useState, type JSX } from "react";
import type { FanRec } from "../api/types";
import type { GenComposition } from "../lib/insights";
import { FilterState, matchFilter } from "../lib/filter";
import CombinedGuess from "../components/CombinedGuess";
import GenerationBreakdown from "./GenerationBreakdown";
import { layoutFan } from "../lib/fanLayout";

// Estimate marker color (matches --guess); SVG presentation attributes can't
// read CSS vars, so the dead-end-wedge outline uses the literal.
const GUESS = "#d99a3c";

const CR = 50;
const RW = 46;
const FS_URL = "https://www.familysearch.org/tree/person/details/";

const polar = (r: number, a: number): [number, number] => [r * Math.cos(a), r * Math.sin(a)];

// Wedge borders are a fixed width, so on deep rings the near-black stroke eats the
// thin wedges and they read progressively darker (and fully black past ~gen 13).
// Scale the stroke with each wedge's mid-arc length so it stays a small fraction:
// gens ≤9 still clamp to the full width (unchanged look), gens ≥10 taper off so the
// color dominates and same-origin neighbors merge into bright bands.
const strokeFor = (r0: number, r1: number, a0: number, a1: number, cap: number) =>
  Math.min(cap, ((r0 + r1) / 2) * (a1 - a0) * 0.12);

function sector(r0: number, r1: number, a0: number, a1: number): string {
  const large = a1 - a0 > Math.PI ? 1 : 0;
  const [x0, y0] = polar(r0, a0);
  const [x1, y1] = polar(r1, a0);
  const [x2, y2] = polar(r1, a1);
  const [x3, y3] = polar(r0, a1);
  return (
    `M${x0.toFixed(2)} ${y0.toFixed(2)} L${x1.toFixed(2)} ${y1.toFixed(2)} ` +
    `A${r1} ${r1} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} ` +
    `L${x3.toFixed(2)} ${y3.toFixed(2)} A${r0} ${r0} 0 ${large} 0 ${x0.toFixed(2)} ${y0.toFixed(2)} Z`
  );
}

const angOf = (g: number, idx: number): [number, number] => {
  const slice = (2 * Math.PI) / Math.pow(2, g);
  const a0 = -Math.PI / 2 + idx * slice;
  return [a0, a0 + slice];
};
const radOf = (g: number): [number, number] => [CR + (g - 1) * RW, CR + g * RW];
const fit = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

export default function FanChart({
  recs,
  root,
  focus,
  filter,
  genComposition,
  onPerson,
}: {
  recs: Record<string, FanRec>;
  root: string;
  // External re-center request (e.g. "View in family tree" from a map pin). A
  // fresh object each time so re-clicking the same person still re-centers.
  focus?: { xref: string } | null;
  // The shared dashboard filter: its generation range caps the fan depth and its
  // country/sex/DNA/year narrow which wedges stay vivid (the rest dim).
  filter: FilterState;
  // Per-generation origin composition for the side panel. Root-relative ("from
  // you") and whole-tree, so it stays put when you dive into a sub-tree.
  genComposition?: GenComposition[];
  // Open the full person page for a wedge. Wedge clicks still re-center (dive);
  // this powers the side-panel "Full details" button for the centered person.
  onPerson?: (xref: string) => void;
}) {
  // The data and filters set the ceiling; the position budget can lower it.
  const maxRings = Object.values(recs).reduce((m, r) => Math.max(m, r.gen ?? 0), 3);
  const ringCeiling = Math.max(3, Math.min(maxRings, filter.genMax));

  const focused = focus?.xref && recs[focus.xref] ? focus.xref : null;
  const [center, setCenter] = useState(focused ?? root);
  const [rings, setRings] = useState(Math.min(8, ringCeiling));
  const [history, setHistory] = useState<string[]>([]);
  const budget = useMemo(() => layoutFan(recs, center, ringCeiling), [recs, center, ringCeiling]);
  const displayRings = Math.min(rings, budget.rings);

  // Re-centering and filters can reduce the safe depth.
  useEffect(() => {
    setRings((r) => Math.min(r, budget.rings));
  }, [budget.rings]);

  // Country/state/sex/DNA/birth-year/generation filter -> dim non-matching wedges
  // (you can't drop a parent from a pedigree, so highlight rather than hide).
  const matches = (r: FanRec) =>
    matchFilter(filter, { br: r.br, nat: r.nat, st: r.st, sex: r.s, dna: r.dna, year: r.y, gen: r.gen });

  // Re-center when an external focus arrives (also covers the case where the
  // chart stays mounted across focus changes). A fresh focus object is required.
  useEffect(() => {
    if (focused) {
      setCenter(focused);
      setHistory([]);
    }
  }, [focus, focused]);

  const c = recs[center];
  if (!c) return <div className="loading">No fan data.</div>;

  const { filled, gaps } = layoutFan(recs, center, displayRings);
  const R = CR + displayRings * RW + 6;

  function dive(x: string) {
    if (x === center) return;
    setHistory((h) => [...h, center]);
    setCenter(x);
  }
  function back() {
    setHistory((h) => {
      if (!h.length) return h;
      setCenter(h[h.length - 1]);
      return h.slice(0, -1);
    });
  }
  function reset() {
    setCenter(root);
    setHistory([]);
  }

  const labels: JSX.Element[] = [];
  for (const nd of filled) {
    if (nd.g === 0 || nd.g > 4) continue;
    const [a0, a1] = angOf(nd.g, nd.idx);
    const [r0, r1] = radOf(nd.g);
    const mid = (a0 + a1) / 2;
    const rm = (r0 + r1) / 2;
    const [tx, ty] = polar(rm, mid);
    let deg = (mid * 180) / Math.PI;
    if (deg > 90 || deg < -90) deg += 180;
    const size = nd.g <= 2 ? 11 : nd.g === 3 ? 9 : 7.5;
    const chars = nd.g <= 2 ? 12 : nd.g === 3 ? 9 : 7;
    labels.push(
      <text
        key={`lbl-${nd.g}-${nd.idx}`}
        className="ftxt"
        transform={`translate(${tx.toFixed(2)} ${ty.toFixed(2)}) rotate(${deg.toFixed(1)})`}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={size}
        opacity={matches(recs[nd.x]) ? 1 : 0.3}
      >
        {fit(recs[nd.x].g, chars)}
      </text>,
    );
  }

  const sub =
    center === root ? "you are here" : c.gen != null ? `gen ${c.gen} back` : "centered here";

  return (
    <div className="fan">
      <div className="fan-side">
        <h2 style={{ marginTop: 0 }}>Centered on</h2>
        <div style={{ fontSize: 16, fontWeight: 600 }}>{c.n}</div>
        <div className="cnt">
          {c.y ? `b. ${c.y}` : "birth unknown"}
          {c.p ? ` · ${c.p}` : ""}
        </div>
        {c.gen != null && (
          <div className="sub" style={{ marginTop: 4 }}>
            {c.gen} generation{c.gen === 1 ? "" : "s"} back from you
          </div>
        )}
        {c.est && (
          <div className="field" style={{ marginTop: 12 }}>
            <span>Likely origin (estimated — not documented)</span>
            <CombinedGuess est={c.est} />
          </div>
        )}
        <div style={{ display: "flex", gap: 8, margin: "12px 0", flexWrap: "wrap" }}>
          <button onClick={back} disabled={!history.length}>
            ← Back
          </button>
          <button onClick={reset}>Reset to me</button>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {onPerson && (
            <button className="btn-primary" onClick={() => onPerson(center)}>
              View full details
            </button>
          )}
          {c.fid && (
            <a className="btn" href={FS_URL + c.fid} target="_blank" rel="noopener noreferrer">
              FamilySearch ↗
            </a>
          )}
        </div>
        <div className="field" style={{ marginTop: 16 }}>
          <span>
            Rings: {displayRings}
            {ringCeiling < maxRings ? ` · capped at gen ${ringCeiling} by the filter` : ""}
          </span>
          <input
            type="range"
            min={3}
            max={budget.rings}
            value={displayRings}
            onChange={(e) => setRings(+e.target.value)}
            style={{ width: "100%", accentColor: "var(--accent)" }}
          />
        </div>
        {budget.limited && (
          <p className="sub">Showing up to {budget.rings} rings to keep the chart responsive.
            Click a wedge to explore that branch further.</p>
        )}
        <p className="sub" style={{ marginTop: 12 }}>
          Click any wedge to re-center and read its names. Gray empty wedges are
          unknown ancestors — where a line dead-ends. The generation table covers
          the whole tree even when the chart's depth is limited.
        </p>

        {genComposition && genComposition.length > 0 && (
          <>
            <h2>Ancestry by generation</h2>
            <div className="sub">
              Each generation has 2ⁿ ancestor slots; missing or untraced ones count
              as unknown. Covers your whole tree — not narrowed by the filters.
            </div>
            <GenerationBreakdown data={genComposition} />
          </>
        )}
      </div>

      <div className="fan-canvas">
        <svg
          viewBox={`${-R} ${-R} ${2 * R} ${2 * R}`}
          preserveAspectRatio="xMidYMid meet"
          style={{ width: "100%", height: "100%", display: "block" }}
        >
          {gaps
            .filter((gp) => gp.g <= displayRings)
            .map((gp, i) => {
              const [a0, a1] = angOf(gp.g, gp.idx);
              const [r0, r1] = radOf(gp.g);
              return (
                <path
                  key={`gap-${i}`}
                  d={sector(r0, r1, a0, a1)}
                  // Empty slots (missing/dead-end ancestors) use a muted slate, not
                  // near-black: deep rings are mostly empty, so this lifts them out of
                  // the background while staying desaturated enough to sit behind the
                  // vivid colored (known) wedges rather than competing with them.
                  fill="#333a47"
                  stroke="#454d5c"
                  strokeWidth={strokeFor(r0, r1, a0, a1, 0.5)}
                />
              );
            })}

          {filled.map((nd) => {
            const r = recs[nd.x];
            // Key by pedigree position, not xref: under pedigree collapse the same
            // ancestor occupies several positions, so xref repeats — duplicate keys
            // make React drop a wedge. (g, idx) is unique per slot.
            const posKey = `${nd.g}-${nd.idx}`;
            if (nd.g === 0) {
              return (
                <circle
                  key={posKey}
                  cx={0}
                  cy={0}
                  r={CR}
                  fill={r.c}
                  stroke="#0b0d10"
                  strokeWidth={2}
                  style={{ cursor: "pointer" }}
                  onClick={() => dive(nd.x)}
                >
                  <title>{r.n}</title>
                </circle>
              );
            }
            const [a0, a1] = angOf(nd.g, nd.idx);
            const [r0, r1] = radOf(nd.g);
            // Dead-end wedges with an estimated origin get a dashed amber outline
            // — an "this is a guess" cue in the same visual language as the badges,
            // so it's never mistaken for the sourced (solid-edged) wedges.
            return (
              <path
                key={posKey}
                d={sector(r0, r1, a0, a1)}
                fill={r.c}
                fillOpacity={matches(r) ? 1 : 0.16}
                stroke={r.est ? GUESS : "#0b0d10"}
                strokeWidth={r.est ? Math.max(0.9, strokeFor(r0, r1, a0, a1, 1.4)) : strokeFor(r0, r1, a0, a1, 0.6)}
                strokeDasharray={r.est ? "2.5 1.5" : undefined}
                style={{ cursor: "pointer" }}
                onClick={() => dive(nd.x)}
              >
                <title>
                  {r.n}
                  {r.y ? ` · b. ${r.y}` : ""}
                  {r.p ? ` · ${r.p}` : ""} · {r.nat}
                  {r.ai ? " ≈ (AI-mapped place)" : ""}
                  {r.est ? ` · ≈ likely ${r.est.label} (estimate)` : ""}
                </title>
              </path>
            );
          })}

          <text className="ftxt" x={0} y={-4} textAnchor="middle" fontSize={13}>
            {fit(c.g, 11)}
          </text>
          <text className="ftxt" x={0} y={13} textAnchor="middle" fontSize={9} opacity={0.7}>
            {sub}
          </text>
          {labels}
        </svg>
      </div>
    </div>
  );
}
