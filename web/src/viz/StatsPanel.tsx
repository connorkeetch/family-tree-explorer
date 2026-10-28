import { useState } from "react";
import type { ReactNode } from "react";
import type {
  Completeness,
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
  const Row = onClick ? "button" : "div";
  return (
    <Row
      className={`row${onClick ? " rowclick" : ""}`}
      type={onClick ? "button" : undefined}
      style={{ width: "100%", textAlign: "left" }}
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
    </Row>
  );
}

// Use the shared person inspector, falling back to the family chart if absent.
function NameLink({
  name,
  xref,
  fid,
  onViewTree,
  onPerson,
}: {
  name: string;
  xref: string | null;
  fid: string | null;
  onViewTree: (xref: string) => void;
  onPerson?: (xref: string) => void;
}) {
  if (!xref) return <>{name}</>;
  return (
    <span className="namelink-wrap">
      <button className="namelink" onClick={() => (onPerson ?? onViewTree)(xref)} title="Open person details">
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
function DupRow({ row, onViewTree, onPerson }: { row: DupGroup; onViewTree: (xref: string) => void; onPerson?: (xref: string) => void }) {
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
            onPerson={onPerson}
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
const gapReason: Record<string, string> = {
  "new-world leaf": "Parents missing",
  "unknown-place": "Birthplace and parents missing",
  "unresolved-place": "Unresolved birthplace; parents missing",
  "copied-place": "Possibly copied birthplace; parents missing",
  "one parent only": "One parent missing",
  "missing record": "Referenced parent missing",
  cycle: "Parent links form a loop",
};
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
  onShowPeople,
}: {
  insights: DerivedInsights & { completeness: Completeness[] };
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
  onShowPeople: (title: string, people: PersonRef[]) => void;
}) {
  const { completeness, surnames, longevity, immigration } = insights;
  const openDrill = onShowPeople;
  // Origin guesses are estimates, not FamilySearch facts -- a toggle hides them
  // entirely so the user can see only documented data. Default on (clearly marked).
  const [showGuesses, setShowGuesses] = useState(true);

  const immByDecade: Record<number, { nat: string; count: number; color: string }[]> = {};
  for (const r of immigration.by_decade) {
    (immByDecade[r.decade] ??= []).push(r);
  }

  const yDeep = deepestOrigin(dna.y_line);
  const mtDeep = deepestOrigin(dna.mt_line);
  const unresolved = people.filter((p) => p.nat === "(untraced)");
  const recordsToCheck = people.filter((p) => p.pc || p.wife?.copied || p.src === 0);
  const missingParents = people.filter((p) => (p.missing_parents ?? 0) > 0);
  const missingParentLinks = missingParents.reduce((sum, p) => sum + (p.missing_parents ?? 0), 0);
  const originGaps = deadends?.top_genuine.filter((d) => d.reason !== "cycle") ?? [];

  return (
    <div className="insights">
      <div className="grid2">
        <Card title="Where are parents missing?">
          <p className="sub">
            Matching your filters · <b>{missingParents.length.toLocaleString()}</b> {missingParents.length === 1 ? "person has" : "people have"}
            <b> {missingParentLinks.toLocaleString()}</b> {missingParentLinks === 1 ? "parent link" : "parent links"} missing from this file.
            Gaps can reflect the export depth; historical records may still exist.
          </p>
          <button onClick={() => openDrill("Matching your filters · People with missing parent links", missingParents)}
            disabled={!missingParents.length}>
            Browse people with missing parents
          </button>
          <details style={{ marginTop: 12 }}>
            <summary>Origin estimates and the gap breakdown</summary>
          {deadendsError ? (
            <div className="err" role="alert">Couldn’t load origin-gap analysis: {deadendsError}</div>
          ) : !deadends ? (
            <div className="sub">Checking gaps in the origin estimates…</div>
          ) : (
            <>
              <div className="sub">
                Whole tree · Imported parent links and places leave <b>{deadends.untraced_pct}%</b> of
                estimated family origins unresolved. {deadends.wall_pct}% is at the deepest imported
                generation ({deadends.wall_generation}); {deadends.genuine_pct}% is in earlier generations.
                Missing information in this file does not establish that historical records end here.
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
                      imported line stops, historical settlement patterns, surname etymology, and the
                      documented origins of same-surname relatives — they are <b>not</b> recorded for
                      these people in your imported records. Treat low confidence as a research hint.
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

              <h2>Why origin estimates stop</h2>
              {Object.entries(deadends.by_reason).map(([reason, pct]) => (
                <Bar key={reason} label={gapReason[reason] ?? reason} frac={pct / 100} color="#9A6324" right={`${pct}%`} />
              ))}
              {originGaps.length > 0 && <h2>Records before the deepest imported generation</h2>}
              {originGaps.slice(0, 12).map((d, i) => (
                <div className="row deadend-row" key={i}>
                  <span className="lbl" style={{ width: "auto", flex: 1 }}>
                    <NameLink name={d.name} xref={d.xref} fid={d.fid} onViewTree={onViewTree} onPerson={onPerson} />
                  </span>
                  <span className="cnt">
                    gen {d.gen} · {d.pct}% · {d.place || "no birthplace"}
                  </span>
                  <span className="cnt">{gapReason[d.reason] ?? d.reason}</span>
                </div>
              ))}
            </>
          )}
          </details>
        </Card>

        <Card title="Which places are unresolved?">
          <p className="sub">Matching your filters · {unresolved.length.toLocaleString()} people have no resolved birth country. A recorded place name can still need checking.</p>
          <button disabled={!unresolved.length} onClick={() => openDrill("Matching your filters · Unresolved birth countries", unresolved)}>Browse people and their places</button>
        </Card>
        <Card title="Which records need checking?">
          <p className="sub">Matching your filters · {recordsToCheck.length.toLocaleString()} records have no source citations, alternative parent claims, or a possibly copied birthplace. These are research prompts, not proof of an error.</p>
          <button disabled={!recordsToCheck.length} onClick={() => openDrill("Matching your filters · Records to check", recordsToCheck)}>Check these records</button>
        </Card>
        {duplicates && duplicates.n_same + duplicates.n_possible > 0 && (
          <Card title="Possible duplicate records">
            <p className="sub">Whole tree · These checks do not narrow with the filters.</p>
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
              <DupRow key={g.records[0].xref} row={g} onViewTree={onViewTree} onPerson={onPerson} />
            ))}
            {duplicates.possible.length > 0 && <h2>Possibly the same</h2>}
            {duplicates.possible.slice(0, 8).map((g) => (
              <DupRow key={g.records.map((r) => r.xref).join()} row={g} onViewTree={onViewTree} onPerson={onPerson} />
            ))}
          </Card>
        )}
      </div>
      <details className="card">
        <summary>Deeper statistics</summary>
        <div className="grid2" style={{ marginTop: 16 }}>
        <Card title="Pedigree completeness">
          <div className="sub">Whole tree · Recorded direct ancestors vs the 2ⁿ possible at each generation. Filters do not change completeness.</div>
          {completeness.map((c) => (
            <Bar
              key={c.gen}
              label={`gen ${c.gen} · ${c.known}/${c.expected}`}
              frac={c.expected ? c.known / c.expected : 0}
              color="var(--accent2)"
              right={`${Math.round((100 * c.known) / c.expected)}%`}
            />
          ))}
        </Card>

        <Card title="Top surnames">
          <div className="sub">Matching your filters · Most common surnames among direct ancestors, colored by dominant origin. Click to list.</div>
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
          <div className="sub">Matching your filters · Median age at death across {longevity.n.toLocaleString()} ancestors with both years. Click a bar to list them.</div>
          {longevity.by_century.length > 0 && <h2>By birth century (15+ recorded lifespans)</h2>}
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
          {longevity.by_origin.length > 0 && <h2>By origin (20+ recorded lifespans)</h2>}
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
          {!longevity.by_century.length && !longevity.by_origin.length && <div className="sub">No group has enough recorded lifespans for comparison: 15 per birth century or 20 per origin are needed.</div>}
        </Card>

        <Card title="Direct family lines">
          <div className="sub" style={{ fontStyle: "italic" }}>
            Whole tree · Father-to-father and mother-to-mother chains. Only the generation range narrows these lists; other filters do not apply.
          </div>
          <div className="sub">
            Father-to-father (Y-DNA): {dna.y_line.length} gens
            {yDeep ? ` · deepest ${yDeep}` : ""}
          </div>
          {dna.y_line.map((p, i) => (
            <div className="row" key={`y${i}`}>
              <span className="sw" style={{ background: p.color }} />
              <span className="lbl" style={{ width: "auto", flex: 1 }}>
                <NameLink name={p.name} xref={p.xref} fid={p.fid} onViewTree={onViewTree} onPerson={onPerson} />
              </span>
              <span className="cnt">
                {p.nat || "—"}
                {p.year ? ` · b.${formatYear(p.year)}` : ""}
              </span>
            </div>
          ))}
          <div className="sub" style={{ marginTop: 10 }}>
            Mother-to-mother (mtDNA): {dna.mt_line.length} gens
            {mtDeep ? ` · deepest ${mtDeep}` : ""}
          </div>
          {dna.mt_line.map((p, i) => (
            <div className="row" key={`mt${i}`}>
              <span className="sw" style={{ background: p.color }} />
              <span className="lbl" style={{ width: "auto", flex: 1 }}>
                <NameLink name={p.name} xref={p.xref} fid={p.fid} onViewTree={onViewTree} onPerson={onPerson} />
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
            Matching your filters · {immigration.total.toLocaleString()} immigrant ancestors (first on each line to leave the Old
            World), by birth decade. Click a decade or an origin to list them.
            {immigration.undated ? ` ${immigration.undated} undated omitted.` : ""}
          </div>
          {Object.keys(immByDecade)
            .map(Number)
            .sort((a, b) => a - b)
            .map((dec) => (
              <div className="row" key={dec}>
                <button
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
                </button>
                <span style={{ flex: 1, display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {immByDecade[dec].map((r) => (
                    <button
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
                    </button>
                  ))}
                </span>
              </div>
            ))}
        </Card>

        <Card title="Pedigree collapse">
          <div className="sub" style={{ fontStyle: "italic" }}>
            Whole tree · An ancestor can occupy several positions when relatives have children together. Only the generation range narrows the couple list; other filters do not apply.
          </div>
          <div className="sub">
            <b>{collapse.n_collapse.toLocaleString()}</b> ancestors sit on more than one line (cousins
            married); <b>{collapse.n_over_attached.toLocaleString()}</b> carry &gt;2 parent records
            (alternative or duplicated parent claims to check).
          </div>
          {collapse.couples.map((c, i) => (
            <div className="row" key={i}>
              <span className="lbl" style={{ width: "auto", flex: 1 }}>
                <NameLink name={c.father} xref={c.fa_xref} fid={c.fa_fid} onViewTree={onViewTree} onPerson={onPerson} />
                {" & "}
                <NameLink name={c.mother} xref={c.mo_xref} fid={c.mo_fid} onViewTree={onViewTree} onPerson={onPerson} />
              </span>
              <span className="cnt">
                {c.lines} lines{c.gen != null ? ` · gen ${c.gen}` : ""}
              </span>
            </div>
          ))}
          {!collapse.couples.length && <div className="sub">none detected</div>}
        </Card>

        </div>
      </details>
    </div>
  );
}
