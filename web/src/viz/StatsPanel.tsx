import { useState } from "react";
import type { ReactNode } from "react";
import type {
  Collapse,
  Dna,
  DeadendsPayload,
  DupGroup,
  DuplicatesPayload,
  Person,
  Immigrant,
  PersonRef,
} from "../api/types";
import type { DerivedInsights } from "../lib/insights";
import { formatYear } from "../lib/year";
import PersonDrawer from "../components/PersonDrawer";
import CombinedGuess from "../components/CombinedGuess";

const FS_URL = "https://www.familysearch.org/tree/person/details/";

// Clickable analytics bar: opening the drill panel shows the people behind it.
function Bar({
  label,
  frac,
  color,
  right,
  onClick,
}: {
  label: string;
  frac: number;
  color: string;
  right: string;
  onClick?: () => void;
}) {
  return (
    <div
      className={`row${onClick ? " rowclick" : ""}`}
      onClick={onClick}
      title={onClick ? "Show the people behind this" : undefined}
    >
      <span className="lbl" style={{ width: 140 }}>
        {label}
      </span>
      <span className="track">
        <span className="fill" style={{ width: `${Math.min(100, frac * 100)}%`, background: color }} />
      </span>
      <span className="pct">{right}</span>
    </div>
  );
}

// An individual ancestor's name, linking to the family-tree fan chart (+ a small
// FamilySearch link). Used wherever a row IS one person (DNA lines, dead-ends,
// collapse couples) rather than an aggregate.
function NameLink({
  name,
  xref,
  fid,
  onViewTree,
}: {
  name: string;
  xref: string | null;
  fid: string | null;
  onViewTree: (xref: string) => void;
}) {
  if (!xref) return <>{name}</>;
  return (
    <span className="namelink-wrap">
      <button className="namelink" onClick={() => onViewTree(xref)} title="Center the family-tree fan chart on this person">
        {name}
      </button>
      {fid && (
        <a className="fsmini" href={FS_URL + fid} target="_blank" rel="noopener noreferrer" title="FamilySearch">
          ↗
        </a>
      )}
    </span>
  );
}

// One person FamilySearch likely holds more than once: every record, each with
// its own fan-chart + FamilySearch links, and the AI verdict in guess styling.
function DupRow({ row, onViewTree }: { row: DupGroup; onViewTree: (xref: string) => void }) {
  const first = row.records[0];
  const same = row.score >= 1.5;
  return (
    <div className="row deadend-row">
      <span className="lbl" style={{ width: "auto", flex: 1 }}>
        {first.name}
        <span className="cnt">{first.year != null ? ` · b.${formatYear(first.year)}` : ""}</span>
      </span>
      <span className="dup-recs">
        {row.records.map((r) => (
          <NameLink
            key={r.xref}
            name={`${r.fid ?? r.xref}${r.gen != null ? ` · gen ${r.gen}` : ""}`}
            xref={r.xref}
            fid={r.fid}
            onViewTree={onViewTree}
          />
        ))}
      </span>
      {row.shared_child && (
        <span className="basis" title="A child in your tree claims more than one of these records as a parent">
          shared child
        </span>
      )}
      <span className="guess-badge" title={`AI score ${row.score.toFixed(2)} on a 0 (different) – 2 (same person) scale`}>
        ≈ {same ? "same person" : "possibly same"}
      </span>
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>{title}</h2>
      {children}
    </div>
  );
}

const surnameLabel = (p: Person) => p.surname.trim() || "(unknown)";
// deepest resolved origin along a (generation-capped) DNA line — recomputed from
// the rows shown, so the header never disagrees with the truncated list.
const deepestOrigin = (line: Dna["y_line"]): string | null =>
  [...line].reverse().find((r) => r.nat)?.nat ?? null;

export default function StatsPanel({
  insights,
  collapse,
  dna,
  deadends,
  deadendsError,
  duplicates,
  people,
  immigrants,
  onViewTree,
  onPerson,
}: {
  insights: DerivedInsights;
  collapse: Collapse;
  dna: Dna;
  deadends: DeadendsPayload | null;
  deadendsError?: string | null;
  duplicates?: DuplicatesPayload | null;
  people: Person[];
  immigrants: Immigrant[];
  onViewTree: (xref: string) => void;
  // Open the full person page from a drill-down list (any insight bucket).
  onPerson?: (xref: string) => void;
}) {
  const { completeness, surnames, longevity, immigration } = insights;
  const [drill, setDrill] = useState<{ title: string; people: PersonRef[] } | null>(null);
  const openDrill = (title: string, rows: PersonRef[]) => setDrill({ title, people: rows });
  // Origin guesses are estimates, not FamilySearch facts -- a toggle hides them
  // entirely so the user can see only documented data. Default on (clearly marked).
  const [showGuesses, setShowGuesses] = useState(true);

  const immByDecade: Record<number, { nat: string; count: number; color: string }[]> = {};
  for (const r of immigration.by_decade) {
    (immByDecade[r.decade] ??= []).push(r);
  }

  const yDeep = deepestOrigin(dna.y_line);
  const mtDeep = deepestOrigin(dna.mt_line);

  return (
    <div className="insights">
      <div className="grid2">
        <Card title="Pedigree completeness">
          <div className="sub">Known direct ancestors vs the 2ⁿ possible at each generation. Click a row to list them.</div>
          {completeness.map((c) => (
            <Bar
              key={c.gen}
              label={`gen ${c.gen} · ${c.known}/${c.expected}`}
              frac={c.expected ? c.known / c.expected : 0}
              color="var(--accent2)"
              right={`${Math.round((100 * c.known) / c.expected)}%`}
              onClick={() =>
                openDrill(
                  `Generation ${c.gen} · ${c.known} direct ancestors`,
                  people.filter((p) => p.dir && p.gen === c.gen),
                )
              }
            />
          ))}
        </Card>

        <Card title="Top surnames">
          <div className="sub">Most common surnames among direct ancestors, colored by dominant origin. Click to list.</div>
          {(() => {
            const max = Math.max(...surnames.map((s) => s.count), 1);
            return surnames.map((s) => (
              <Bar
                key={s.surname}
                label={s.surname}
                frac={s.count / max}
                color={s.color}
                right={String(s.count)}
                onClick={() =>
                  openDrill(
                    `${s.surname} · ${s.count} ancestors`,
                    people.filter((p) => p.dir && p.gen !== 0 && surnameLabel(p) === s.surname),
                  )
                }
              />
            ));
          })()}
        </Card>

        <Card title="Longevity">
          <div className="sub">Median age at death across {longevity.n.toLocaleString()} ancestors with both years. Click a bar to list them.</div>
          <h2>By birth century</h2>
          {longevity.by_century.map((r) => {
            const cent = parseInt(r.label, 10); // "1800s" -> 1800
            return (
              <Bar
                key={r.label}
                label={r.label}
                frac={r.median / 90}
                color="var(--accent2)"
                right={`${r.median} yrs (${r.n})`}
                onClick={() =>
                  openDrill(
                    `Born ${r.label} · ${r.n} with a known lifespan`,
                    people.filter(
                      (p) => p.gen !== 0 && p.age != null && !!p.year && Math.floor(p.year! / 100) * 100 === cent,
                    ),
                  )
                }
              />
            );
          })}
          <h2>By origin (n ≥ 20)</h2>
          {longevity.by_origin.map((r) => (
            <Bar
              key={r.label}
              label={r.label}
              frac={r.median / 90}
              color={r.color || "var(--accent2)"}
              right={`${r.median} yrs (${r.n})`}
              onClick={() =>
                openDrill(
                  `${r.label} · ${r.n} with a known lifespan`,
                  people.filter((p) => p.gen !== 0 && p.age != null && p.nat === r.label),
                )
              }
            />
          ))}
          {!longevity.by_origin.length && <div className="sub">not enough data</div>}
        </Card>

        <Card title="Direct DNA lines">
          <div className="sub" style={{ fontStyle: "italic" }}>
            A single ancestral chain — narrows by the generation filter only, not branch/country/sex/DNA.
          </div>
          <div className="sub">
            ♂ Patrilineal (Y-DNA): {dna.y_line.length} gens
            {yDeep ? ` · deepest ${yDeep}` : ""}
          </div>
          {dna.y_line.map((p, i) => (
            <div className="row" key={`y${i}`}>
              <span className="sw" style={{ background: p.color }} />
              <span className="lbl" style={{ width: "auto", flex: 1 }}>
                <NameLink name={p.name} xref={p.xref} fid={p.fid} onViewTree={onViewTree} />
              </span>
              <span className="cnt">
                {p.nat || "—"}
                {p.year ? ` · b.${formatYear(p.year)}` : ""}
              </span>
            </div>
          ))}
          <div className="sub" style={{ marginTop: 10 }}>
            ♀ Matrilineal (mtDNA): {dna.mt_line.length} gens
            {mtDeep ? ` · deepest ${mtDeep}` : ""}
          </div>
          {dna.mt_line.map((p, i) => (
            <div className="row" key={`mt${i}`}>
              <span className="sw" style={{ background: p.color }} />
              <span className="lbl" style={{ width: "auto", flex: 1 }}>
                <NameLink name={p.name} xref={p.xref} fid={p.fid} onViewTree={onViewTree} />
              </span>
              <span className="cnt">
                {p.nat || "—"}
                {p.year ? ` · b.${formatYear(p.year)}` : ""}
              </span>
            </div>
          ))}
        </Card>

        <Card title="Immigration era">
          <div className="sub">
            {immigration.total.toLocaleString()} immigrant ancestors (first on each line to leave the Old
            World), by birth decade. Click a decade or an origin to list them.
            {immigration.undated ? ` ${immigration.undated} undated omitted.` : ""}
          </div>
          {Object.keys(immByDecade)
            .map(Number)
            .sort((a, b) => a - b)
            .map((dec) => (
              <div className="row" key={dec}>
                <span
                  className="lbl rowclick"
                  onClick={() =>
                    openDrill(
                      `Immigrants born ${dec}s`,
                      immigrants.filter((im) => im.year != null && Math.floor(im.year / 10) * 10 === dec),
                    )
                  }
                  title="Show these immigrants"
                >
                  {dec}s
                </span>
                <span style={{ flex: 1, display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {immByDecade[dec].map((r) => (
                    <span
                      key={r.nat}
                      className="cnt chipclick"
                      style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                      onClick={() =>
                        openDrill(
                          `${r.nat} immigrants born ${dec}s`,
                          immigrants.filter(
                            (im) => im.origin === r.nat && im.year != null && Math.floor(im.year / 10) * 10 === dec,
                          ),
                        )
                      }
                      title={`Show the ${r.nat} immigrants of the ${dec}s`}
                    >
                      <span className="sw" style={{ background: r.color, width: 9, height: 9 }} />
                      {r.nat} {r.count}
                    </span>
                  ))}
                </span>
              </div>
            ))}
        </Card>

        <Card title="Pedigree collapse">
          <div className="sub" style={{ fontStyle: "italic" }}>
            Whole-tree totals — the couple list narrows by the generation filter only, not branch/country/sex/DNA.
          </div>
          <div className="sub">
            <b>{collapse.n_collapse.toLocaleString()}</b> ancestors sit on more than one line (cousins
            married); <b>{collapse.n_over_attached.toLocaleString()}</b> carry &gt;2 parent records
            (un-merged duplicates).
          </div>
          {collapse.couples.map((c, i) => (
            <div className="row" key={i}>
              <span className="lbl" style={{ width: "auto", flex: 1 }}>
                <NameLink name={c.father} xref={c.fa_xref} fid={c.fa_fid} onViewTree={onViewTree} />
                {" & "}
                <NameLink name={c.mother} xref={c.mo_xref} fid={c.mo_fid} onViewTree={onViewTree} />
              </span>
              <span className="cnt">
                {c.lines} lines{c.gen != null ? ` · gen ${c.gen}` : ""}
              </span>
            </div>
          ))}
          {!collapse.couples.length && <div className="sub">none detected</div>}
        </Card>

        <Card title="Where the trail goes cold">
          {deadendsError ? (
            <div className="err">Couldn’t load dead-end analysis: {deadendsError}</div>
          ) : !deadends ? (
            <div className="sub">Analyzing where lines end…</div>
          ) : (
            <>
              <div className="sub">
                <b>{deadends.untraced_pct}%</b> of you is untraced. Of that, {deadends.wall_pct}% hits the
                gen-{deadends.wall_generation} pull wall (a deeper pull may extend it) and {deadends.genuine_pct}% are
                genuine dead-ends (records truly end).
              </div>

              <label className="guess-toggle">
                <input
                  type="checkbox"
                  checked={showGuesses}
                  onChange={(e) => setShowGuesses(e.target.checked)}
                />
                Show origin guesses
              </label>

              {showGuesses && (
                <>
                  <div className="guess-note">
                    <span aria-hidden>≈</span>
                    <span>
                      <b>Estimates, not documented.</b> The guesses below are inferred from where each
                      line dead-ends, historical settlement patterns, surname etymology, and the
                      documented origins of same-surname relatives — they are <b>not</b> recorded for
                      these people in your FamilySearch data. Treat low confidence as a research hint.
                    </span>
                  </div>

                  {deadends.likely_origin.length > 0 && (
                    <>
                      <div className="guess-h">
                        <span aria-hidden>≈</span> Likely origins of the untraced {deadends.untraced_pct}%
                      </div>
                      {deadends.likely_origin.map((o) => {
                        const none = o.confidence === "none";
                        return (
                          <div
                            className={`row guess-row${none ? " conf-none" : ""}`}
                            key={o.label}
                            title={o.rationale}
                          >
                            <span className="lbl" style={{ width: 168 }}>
                              {none ? "?" : "≈"} {o.label}
                            </span>
                            <span className="track">
                              <span
                                className="fill"
                                style={{
                                  width: `${Math.min(100, o.pct)}%`,
                                  background: none ? "var(--guess-dim)" : "var(--guess)",
                                }}
                              />
                            </span>
                            <span className="pct">
                              {o.pct}% · {o.confidence}
                            </span>
                          </div>
                        );
                      })}
                    </>
                  )}
                </>
              )}

              <h2>Why lines end</h2>
              {Object.entries(deadends.by_reason).map(([reason, pct]) => (
                <Bar key={reason} label={reason} frac={pct / 100} color="#9A6324" right={`${pct}%`} />
              ))}
              <h2>Top genuine dead-ends</h2>
              {deadends.top_genuine.slice(0, 12).map((d, i) => (
                <div className="row deadend-row" key={i}>
                  <span className="lbl" style={{ width: "auto", flex: 1 }}>
                    <NameLink name={d.name} xref={d.xref} fid={d.fid} onViewTree={onViewTree} />
                  </span>
                  <span className="cnt">
                    gen {d.gen} · {d.pct}% · {d.place || "no birthplace"}
                  </span>
                  {showGuesses && <CombinedGuess est={d.origin_estimate} />}
                </div>
              ))}
            </>
          )}
        </Card>

        {duplicates && duplicates.n_same + duplicates.n_possible > 0 && (
          <Card title="Possible duplicate records">
            <div className="guess-note">
              <span aria-hidden>≈</span>
              <span>
                <b>AI judgment, not a FamilySearch fact.</b> These look like one person entered more than
                once (same name and birth year, plus matching parents, places, dates or a shared child).
                Nothing is merged here — open the records on FamilySearch and merge them there if they
                really are one person.
              </span>
            </div>
            <div className="sub">
              <b>{duplicates.n_same}</b> people look recorded more than once ({duplicates.n_same_records}{" "}
              records); {duplicates.n_possible} more {duplicates.n_possible === 1 ? "pair" : "pairs"} might
              be. Closest generations first.
            </div>
            {duplicates.same.length > 0 && <h2>Likely the same person</h2>}
            {duplicates.same.slice(0, 12).map((g) => (
              <DupRow key={g.records[0].xref} row={g} onViewTree={onViewTree} />
            ))}
            {duplicates.possible.length > 0 && <h2>Possibly the same</h2>}
            {duplicates.possible.slice(0, 8).map((g) => (
              <DupRow key={g.records.map((r) => r.xref).join()} row={g} onViewTree={onViewTree} />
            ))}
          </Card>
        )}
      </div>

      {drill && (
        <PersonDrawer
          title={drill.title}
          people={drill.people}
          onViewTree={onViewTree}
          onOpenPerson={onPerson}
          onClose={() => setDrill(null)}
        />
      )}
    </div>
  );
}
