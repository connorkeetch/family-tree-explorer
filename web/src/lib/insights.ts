// Filtered insight cards and migration flows are derived in the browser.
// Pedigree completeness belongs to the whole-tree deriveGenComposition result.
//
// The graph-walk stats (pedigree collapse, the Y/mt DNA lineages) can't be
// recomputed without parent links, so those stay server-precomputed in `stats`
// and the dashboard only generation-caps them.

import type {
  Person,
  Immigrant,
  Colors,
  SurnameRow,
  Longevity,
  LifeRow,
  Immigration,
  ImmRow,
  SankeyData,
  SankeyFlow,
  FanRec,
} from "../api/types";

const UNTRACED = "(untraced)";

function median(xs: number[]): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
const round1 = (x: number) => Math.round(x * 10) / 10;

function bucket<K>(m: Map<K, number[]>, k: K, v: number): void {
  const a = m.get(k);
  if (a) a.push(v);
  else m.set(k, [v]);
}

function inc<K>(m: Map<K, number>, k: K, by = 1): void {
  m.set(k, (m.get(k) || 0) + by);
}

export interface DerivedInsights {
  surnames: SurnameRow[];
  longevity: Longevity;
  immigration: Immigration;
}

export interface GenSegment {
  name: string;
  count: number;
  pct: number; // share of the 2^gen slots at this generation
  color: string;
}

export interface GenComposition {
  gen: number; // 0 = you, 1 = parents, 2 = grandparents, ...
  slots: number; // 2^gen ancestor slots at this generation
  known: number; // occupied ancestor slots, including repeated ancestors
  segments: GenSegment[]; // resolved origins (count desc) + a trailing "Unknown"
}

export function deriveInsights(
  people: Person[],
  immigrants: Immigrant[],
  colors: Colors,
): DerivedInsights {
  // --- top surnames (direct line, excluding root), by dominant resolved origin -
  const surCount = new Map<string, number>();
  const surOrigin = new Map<string, Map<string, number>>();
  for (const p of people) {
    if (!p.dir || p.gen === 0) continue;
    const s = p.surname.trim() || "(unknown)";
    inc(surCount, s);
    if (p.nat !== UNTRACED) {
      let o = surOrigin.get(s);
      if (!o) surOrigin.set(s, (o = new Map()));
      inc(o, p.nat);
    }
  }
  const surnames: SurnameRow[] = [...surCount.entries()]
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    .slice(0, 12)
    .map(([surname, count]) => {
      // dominant = highest count; first-seen wins a tie (insertion-ordered Map).
      let dom = "";
      let best = 0;
      const o = surOrigin.get(surname);
      if (o) for (const [lbl, c] of o) if (c > best) { best = c; dom = lbl; }
      return { surname, count, color: colors[dom] || "#6b7280" };
    });

  // --- longevity: median lifespan by birth century and by origin --------------
  // NB: over ALL non-root people (collaterals included), matching _stats — not
  // just the direct line. A branch/DNA filter naturally narrows this to the line.
  const lifeCent = new Map<number, number[]>();
  const lifeNat = new Map<string, number[]>();
  let nLife = 0;
  for (const p of people) {
    if (p.gen === 0) continue;
    if (p.age == null) continue;
    nLife++;
    if (p.year) bucket(lifeCent, Math.floor(p.year / 100) * 100, p.age);
    if (p.nat !== UNTRACED) bucket(lifeNat, p.nat, p.age);
  }
  const by_century: LifeRow[] = [...lifeCent.entries()]
    .sort((a, b) => a[0] - b[0])
    .filter(([, v]) => v.length >= 15)
    .map(([c, v]) => ({ label: `${c}s`, median: round1(median(v)), n: v.length }));
  const by_origin: LifeRow[] = [...lifeNat.entries()]
    .filter(([, v]) => v.length >= 20)
    .sort((a, b) => median(b[1]) - median(a[1]))
    .map(([k, v]) => ({
      label: k,
      median: round1(median(v)),
      n: v.length,
      color: colors[k] || "#4363d8",
    }));
  const longevity: Longevity = { n: nLife, by_century, by_origin };

  return {
    surnames,
    longevity,
    immigration: deriveImmigration(immigrants, colors),
  };
}

// --- immigration by birth decade & origin (from the filtered immigrant rows) ---
function deriveImmigration(immigrants: Immigrant[], colors: Colors): Immigration {
  const decNat = new Map<number, Map<string, number>>();
  let undated = 0;
  for (const im of immigrants) {
    if (im.year == null) {
      undated++;
      continue;
    }
    const dec = Math.floor(im.year / 10) * 10;
    let m = decNat.get(dec);
    if (!m) decNat.set(dec, (m = new Map()));
    inc(m, im.origin);
  }
  const by_decade: ImmRow[] = [];
  for (const dec of [...decNat.keys()].sort((a, b) => a - b)) {
    for (const [nat, count] of [...decNat.get(dec)!.entries()].sort((a, b) => b[1] - a[1])) {
      by_decade.push({ decade: dec, nat, count, color: colors[nat] || "#6b7280" });
    }
  }
  return { by_decade, undated, total: immigrants.length };
}

// API mirror: core/payloads.py::_migration_labels; tests/fixtures/migration.json locks parity.
// Keep <=8 categories named; otherwise top7 + Other. Parenthesized unknowns stay named.
// Ties use UTF-16 ordinal label order, independent of locale.
function migrationLabels(immigrants: Immigrant[]) {
  const origins = new Map<string, number>();
  const settlements = new Map<string, number>();
  for (const im of immigrants) {
    inc(origins, im.origin);
    inc(settlements, im.settlement);
  }
  const labels = (totals: Map<string, number>, other: string) => {
    const ranked = [...totals].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    const kept = new Set((ranked.length <= 8 ? ranked : ranked.slice(0, 7)).map(([name]) => name));
    return (name: string) => kept.has(name) || name.startsWith("(") ? name : other;
  };
  return { origin: labels(origins, "Other origins"), settlement: labels(settlements, "Other states") };
}

// --- migration Sankey: origin -> first New-World settlement ------------------
// Nested maps (origin -> settlement -> count) avoid any composite string key, so
// multi-word labels like "New York" / "American (USA)" need no escaping.
export function deriveSankey(immigrants: Immigrant[], colors: Colors): SankeyData {
  const raw = new Map<string, Map<string, number>>();
  for (const im of immigrants) {
    let m = raw.get(im.origin);
    if (!m) raw.set(im.origin, (m = new Map()));
    inc(m, im.settlement);
  }
  const labels = migrationLabels(immigrants);
  const flows = new Map<string, Map<string, number>>();
  for (const [o, sm] of raw) {
    const oo = labels.origin(o);
    let fm = flows.get(oo);
    if (!fm) flows.set(oo, (fm = new Map()));
    for (const [s, c] of sm) {
      inc(fm, labels.settlement(s), c);
    }
  }
  const rows: SankeyFlow[] = [];
  for (const [origin, sm] of flows) {
    for (const [settlement, count] of sm) {
      rows.push({ origin, settlement, count, color: colors[origin] || "#6b7280" });
    }
  }
  // count desc, then a stable label tiebreak so the array is deterministic
  // regardless of input order (the Sankey re-sorts for layout either way).
  rows.sort(
    (a, b) =>
      b.count - a.count ||
      (a.origin < b.origin ? -1 : a.origin > b.origin ? 1 : a.settlement < b.settlement ? -1 : a.settlement > b.settlement ? 1 : 0),
  );
  let total = 0;
  let settled = 0;
  for (const r of rows) {
    total += r.count;
    if (!r.settlement.startsWith("(")) settled += r.count;
  }
  return { flows: rows, total, settled };
}

// Resolve chart nodes/ribbons against the same filtered people and grouping.
export function sankeyMembers(
  immigrants: Immigrant[],
  sel: { origin?: string; settlement?: string },
): Immigrant[] {
  const labels = migrationLabels(immigrants);
  return immigrants.filter(
    (im) =>
      (sel.origin == null || labels.origin(im.origin) === sel.origin) &&
      (sel.settlement == null || labels.settlement(im.settlement) === sel.settlement),
  );
}

// --- per-generation origin composition (the fan chart's textual companion) -----
// Count positions through selected parents, combining repeated ancestors at each
// generation instead of expanding every pedigree path. Missing slots stay unknown.
const UNKNOWN_COLOR = "#6b7280";

export function deriveGenComposition(
  recs: Record<string, FanRec>, root: string | null, colors: Colors,
): GenComposition[] {
  if (!root || !recs[root]) return [];
  const parents = new Map<string, string[]>();
  const active = new Set<string>();
  const done = new Set<string>();
  const stack = [{ xref: root, leaving: false }];
  while (stack.length) {
    const { xref, leaving } = stack.pop()!;
    if (leaving) {
      active.delete(xref);
      done.add(xref);
      continue;
    }
    if (done.has(xref)) continue;
    active.add(xref);
    stack.push({ xref, leaving: true });
    const links: string[] = [];
    parents.set(xref, links);
    for (const p of [recs[xref].mo, recs[xref].fa]) {
      if (!p || !recs[p] || active.has(p)) continue;
      links.push(p);
      stack.push({ xref: p, leaving: false });
    }
  }
  let positions = new Map([[root, 1]]);
  const out: GenComposition[] = [];
  for (let g = 0; positions.size; g++) {
    const slots = 2 ** g;
    const m = new Map<string, number>();
    const next = new Map<string, number>();
    let known = 0;
    for (const [xref, count] of positions) {
      known += count;
      const nat = recs[xref].nat;
      if (nat !== UNTRACED) inc(m, nat, count);
      for (const p of parents.get(xref) || []) inc(next, p, count);
    }
    const segments: GenSegment[] = [...m.entries()]
      .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
      .map(([name, count]) => ({ name, count, pct: (100 * count) / slots,
        color: colors[name] || UNKNOWN_COLOR }));
    const resolved = segments.reduce((s, x) => s + x.count, 0);
    const unknown = slots - resolved;
    if (unknown > 0) {
      segments.push({
        name: "Unknown",
        count: unknown,
        pct: (100 * unknown) / slots,
        color: colors[UNTRACED] || UNKNOWN_COLOR,
      });
    }
    out.push({ gen: g, slots, known, segments });
    positions = next;
  }
  return out;
}
