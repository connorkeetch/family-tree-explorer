import { useMemo, useRef } from "react";
import type { Colors, FanRec, Person } from "../api/types";
import { useFocusTrap } from "../lib/useFocusTrap";
import { lineageOf } from "../lib/lineage";
import { formatYear } from "../lib/year";
import AiOrigin from "./AiOrigin";

const FS_URL = "https://www.familysearch.org/tree/person/details/";

// gp quadrant codes (core/analyze_origins.branch_tags) -> a readable line.
const GP_SIDE: Record<string, string> = {
  FF: "father's father's line",
  FM: "father's mother's line",
  MF: "mother's father's line",
  MM: "mother's mother's line",
};

const WIFE_WHY =
  "Old registers often recorded a wife under her husband's name (\"Mrs. Charles Baker\"), " +
  "and FamilySearch holds her as a woman with his name — often with his birthplace copied " +
  "in. Her origin isn't counted from a copied birthplace; any estimate is marked as one.";

const PARENTS_WHY =
  "FamilySearch lists more than one set of parents for this person, and no date or " +
  "completeness check rules any of them out. The parents shown are one claim, not settled fact.";

/** Which of several claimed parent couples we follow, and on what basis. */
function ParentsNote({ pc }: { pc: NonNullable<Person["pc"]> }) {
  const others = pc.claims - 1;
  if (!pc.decided)
    return (
      <span className="guess-badge conf-none" title={PARENTS_WHY}>
        contested · {pc.claims} parent claims
        {pc.prob == null ? ", picked by record ID" : ", AI undecided"}
      </span>
    );
  return (
    <span className="guess-badge" title={PARENTS_WHY}>
      ≈ {pc.changed ? "AI picked these" : "AI favours these"} over {others} other claim{others === 1 ? "" : "s"}
      <span className="conf">{Math.round((pc.prob ?? 0) * 100)}%</span>
    </span>
  );
}

function trunc(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/**
 * The person "page": everything we hold on one ancestor — vital facts, origin,
 * family side, sources/memories — plus a jump to their fan chart, a FamilySearch
 * link, and the lineage line showing how you descend from them and through whom.
 * Reuses the shared `.modal` shell. Opened from anywhere a person is clicked; can
 * be stacked over a people list (then `onBack` returns to it). Closes on ✕,
 * Escape, or backdrop click.
 */
export default function PersonModal({
  person: p,
  recs,
  root,
  colors,
  onClose,
  onViewTree,
  onOpenPerson,
  onBack,
}: {
  person: Person;
  recs: Record<string, FanRec> | null;
  root: string | null;
  colors: Colors;
  onClose: () => void;
  onViewTree: (xref: string) => void;
  onOpenPerson: (xref: string) => void;
  onBack?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, onClose);

  const lineage = useMemo(
    () => (recs && root ? lineageOf(p.xref, recs, root) : null),
    [recs, root, p.xref],
  );

  const sexLabel = p.sex === "M" ? "Male" : p.sex === "F" ? "Female" : null;
  const genLabel =
    p.gen === 0
      ? "starting person"
      : p.gen != null
        ? `${p.gen} generation${p.gen === 1 ? "" : "s"} back`
        : p.dir
          ? "on the starting person’s direct line"
          : "relative";
  const side =
    p.br === "P" ? "Father’s side" : p.br === "M" ? "Mother’s side" : null;
  const quadrant = GP_SIDE[p.gp] ? `${GP_SIDE[p.gp]} of the starting person` : null;

  const badges: { label: string; cls: string }[] = [];
  if (p.imm) badges.push({ label: "Immigrant ancestor", cls: "pm-badge-imm" });
  if (p.dna.includes("Y")) badges.push({ label: "Y-DNA line", cls: "pm-badge-dna" });
  if (p.dna.includes("mt")) badges.push({ label: "mtDNA line", cls: "pm-badge-dna" });
  if (side) badges.push({ label: side, cls: "pm-badge-side" });

  // Headline numbers — only the ones we actually know.
  const kpis: { value: string; label: string }[] = [];
  if (p.year != null) kpis.push({ value: formatYear(p.year), label: "born" });
  if (p.dyear != null) kpis.push({ value: formatYear(p.dyear), label: "died" });
  if (p.age != null) kpis.push({ value: `${p.age} yrs`, label: "lifespan" });
  if (p.gen != null) kpis.push({ value: `gen ${p.gen}`, label: "from starting person" });

  // Fact rows — label/value pairs, present-only.
  const facts: { k: string; v: React.ReactNode }[] = [];
  if (sexLabel) facts.push({ k: "Sex", v: sexLabel });
  facts.push({
    k: "Origin",
    v: (
      <>
        <span className="sw" style={{ background: p.color, width: 9, height: 9 }} /> {p.nat}{" "}
        <AiOrigin ai={p.ai} />
      </>
    ),
  });
  if (p.pc) facts.push({ k: "Parents", v: <ParentsNote pc={p.pc} /> });
  if (p.st) facts.push({ k: "U.S. state of birth", v: p.st });
  if (p.wife)
    facts.push({
      k: "Name on record",
      v: (
        <>
          {p.wife.fs_name}{" "}
          <span className="guess-badge conf-none" title={WIFE_WHY}>
            her husband&rsquo;s name — her own is unknown
          </span>
        </>
      ),
    });
  if (p.place) facts.push({ k: "Birthplace", v: trunc(p.place, 64) });
  if (p.wife?.copied)
    facts.push({
      k: "Birthplace",
      v: (
        <span className="guess-badge conf-none" title={WIFE_WHY}>
          only her husband&rsquo;s, copied into her record — not counted
        </span>
      ),
    });
  if (p.dplace) facts.push({ k: "Place of death", v: trunc(p.dplace, 64) });
  if (side || quadrant)
    facts.push({ k: "Family side", v: [side, quadrant].filter(Boolean).join(" · ") });
  facts.push({ k: "Sources", v: `${p.src.toLocaleString()} · ${p.mem.toLocaleString()} memories` });
  if (p.fid) facts.push({ k: "FamilySearch ID", v: <span className="mono">{p.fid}</span> });

  const linName = (xref: string) => (recs && recs[xref] ? recs[xref].n : xref);
  const linYear = (xref: string) => (recs && recs[xref] ? recs[xref].y : null);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${p.name} — person detail`}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="modal-close" aria-label="Close" onClick={onClose}>
          ×
        </button>
        {onBack && (
          <button className="pm-back" onClick={onBack}>
            ← Back to list
          </button>
        )}

        <h2 className="modal-title" style={{ marginTop: onBack ? 6 : 0 }}>
          {p.name}
        </h2>
        <div className="modal-nats">
          {[sexLabel, p.nat, genLabel].filter(Boolean).join(" · ")}
        </div>

        {badges.length > 0 && (
          <div className="pm-badges">
            {badges.map((b) => (
              <span key={b.label} className={`pm-badge ${b.cls}`}>
                {b.label}
              </span>
            ))}
          </div>
        )}

        {kpis.length > 0 && (
          <div className="kpis">
            {kpis.map((k) => (
              <div className="kpi" key={k.label}>
                <b>{k.value}</b>
                <span>{k.label}</span>
              </div>
            ))}
          </div>
        )}

        <div className="pm-actions">
          <button className="btn-primary" onClick={() => onViewTree(p.xref)}>
            Open in family tree
          </button>
          {p.fid && (
            <a className="btn" href={FS_URL + p.fid} target="_blank" rel="noopener noreferrer">
              FamilySearch ↗
            </a>
          )}
        </div>

        <dl className="person-facts">
          {facts.map((f) => (
            <div className="pf-row" key={f.k}>
              <dt>{f.k}</dt>
              <dd>{f.v}</dd>
            </div>
          ))}
        </dl>

        <h2 className="modal-sec">Relationship to the starting person</h2>
        {lineage && lineage.length > 1 ? (
          <>
            <div className="sub">
              {lineage.length - 1} generation{lineage.length - 1 === 1 ? "" : "s"} — from the starting person to{" "}
              {p.name.split(" ")[0] || "them"}.
            </div>
            <ol className="lineage">
              {lineage.map((step, i) => {
                const isTarget = i === lineage.length - 1;
                const rel = step.rel
                  ? step.rel === "father"
                    ? "Father"
                    : "Mother"
                  : "Starting person";
                const yr = linYear(step.xref);
                return (
                  <li
                    key={`${step.xref}-${i}`}
                    className={"lin-row" + (isTarget ? " lin-target" : "")}
                  >
                    <span className="lin-rel">{rel}</span>
                    {isTarget ? (
                      <span className="lin-name">
                        {p.name}
                        {yr ? <span className="cnt"> · b.{yr}</span> : null}
                        <span className="lin-here"> — this person</span>
                      </span>
                    ) : (
                      <button className="lin-name link-btn" onClick={() => onOpenPerson(step.xref)}>
                        {linName(step.xref)}
                        {yr ? <span className="cnt"> · b.{yr}</span> : null}
                      </button>
                    )}
                  </li>
                );
              })}
            </ol>
          </>
        ) : lineage && lineage.length === 1 ? (
          <div className="sub">This is the starting person for this analysis.</div>
        ) : recs ? (
          <div className="sub">
            This record is outside the starting person’s traced ancestral line.
          </div>
        ) : (
          <div className="sub">Relationship paths load with the family tree…</div>
        )}
      </div>
    </div>
  );
}
