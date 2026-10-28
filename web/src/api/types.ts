// TypeScript mirror of the JSON payloads from core/payloads.py.
// Kept hand-written (rather than generated) while the shape is still settling.

export type Colors = Record<string, string>;

export interface UserOut {
  id: number;
  email: string;
}

export interface TreeSummary {
  id: string;
  meta: TreeMeta;
  created_at: string | null;
}

export interface TreeMeta {
  root: string | null;
  root_xref: string | null;
  root_fid: string | null;
  n_people: number;
  n_direct: number;
  max_gen: number;
  n_coords: number;
  total_sources: number;
  total_memories: number;
  living_count: number;
  source_files?: string[];
}

export interface StartingPerson {
  id: string;
  name: string;
  year: number | null;
  place: string | null;
}

export interface ImportPreview {
  people: StartingPerson[];
  suggested_root: string | null;
  candidate_count: number;
}

export interface TreeCreated {
  id: string;
  meta: TreeMeta;
}

export interface OriginItem {
  name: string;
  pct: number;
}

export interface ModelBreakdown {
  breakdown: OriginItem[];
  untraced_pct?: number;
  considered?: number;
}

export interface Models {
  immigrant: ModelBreakdown;
  weighted: ModelBreakdown;
  headcount: ModelBreakdown;
}

export interface CountryDatum {
  count: number;
  immw: number;
  deepw: number;
}

// A [label, count] pair, as emitted by core.payloads._country_details.
export type Tally = [string, number];

export interface CountryAncestor {
  xref?: string;
  year: number;
  gen: number | null;
  name: string;
  place: string | null;
}

export interface CountryDetail {
  nats: Tally[];
  total: number;
  by_gen: Tally[];
  earliest: CountryAncestor | null;
  latest: CountryAncestor | null;
  imm: number;
  imm_span: [number, number] | null;
  settle: Tally[];
  branch: { P: number; M: number };
  surnames: Tally[];
  places: Tally[];
  median_life: number | null;
  life_n: number;
}

export interface OriginsSummary {
  meta: TreeMeta;
  models: Models;
  colors: Colors;
  country_data: Record<string, CountryDatum>;
  cycles: string[];
  unresolved_places: { place: string; count: number; immigrant_pct: number }[];
}

// One canonical row per person -- the single array the SPA filters. The map
// pins, selection bars, insights cards, and migration flows are all derived
// from the filtered result (see web/src/lib/insights.ts), so one control narrows
// every view at once. Coordinates are present-only: birth lat/lon, death
// dlat/dlon (the map's birth/death toggle picks which).
export interface Person {
  name: string;
  nm: string; // lowercased name, for client-side search
  surname: string;
  xref: string;
  fid: string | null;
  gen: number | null;
  sex: string;
  nat: string;
  iso: string;
  st?: string; // US state of birth (American-born ancestors only)
  color: string;
  br: string;
  gp: string;
  dna: string;
  imm: boolean;
  dir: boolean; // on the direct ancestral line
  year: number | null;
  age: number | null;
  missing_parents?: number;
  src: number;
  mem: number;
  lat?: number;
  lon?: number;
  place?: string | null;
  dlat?: number;
  dlon?: number;
  dplace?: string | null;
  dyear?: number | null;
  // AI (Jev) answer for a birthplace the rules couldn't map. used = it's what
  // `nat` shows (high confidence); otherwise a display-only guess.
  ai?: { label: string; conf: number; used: boolean };
  // Contested parents: 2+ parent couples no date/completeness check separates.
  // prob = Jev's averaged P(chosen couple) (null when Jev hasn't been asked);
  // decided = it cleared the bar; changed = it overturned the record-ID order.
  pc?: { claims: number; prob: number | null; decided: boolean; changed: boolean };
  // A wife recorded under her husband's name: the name FamilySearch holds, and
  // whether her birthplace is his, copied in (then not counted or pinned).
  wife?: { fs_name: string; copied: boolean };
}

// One row per immigrant ancestor (a superset of arcs -- no coordinate needed).
// Powers the migration Sankey and the immigration-by-decade insight.
export interface Immigrant {
  origin: string;
  settlement: string;
  nat: string;
  color: string;
  year: number | null;
  gen: number | null;
  br: string;
  sex: string;
  dna: string;
  name: string;
  xref: string;
  fid: string | null;
}

export interface Arc {
  from: [number, number];
  to: [number, number];
  fn: string;
  tn: string;
  nat: string;
  color: string;
  year: number | null;
  br: string;
  sex: string;
  dna: string;
  gen: number | null;
}

export interface Ranges {
  yr_lo: number;
  yr_hi: number;
  dec_lo: number;
  dec_hi: number;
  has_years: boolean;
  gen_lo: number;
  gen_hi: number;
  src_max: number;
  mem_max: number;
}

export interface SankeyFlow {
  origin: string;
  settlement: string;
  count: number;
  color: string;
}

export interface SankeyData {
  flows: SankeyFlow[];
  total: number;
  settled: number;
}

export interface Completeness {
  gen: number;
  known: number;
  expected: number;
}

export interface SurnameRow {
  surname: string;
  count: number;
  color: string;
}

export interface CollapseCouple {
  father: string;
  mother: string;
  fa_xref: string;
  fa_fid: string | null;
  mo_xref: string;
  mo_fid: string | null;
  lines: number;
  gen: number | null;
}

// Minimal shape the PersonDrawer renders + links from (both Person and Immigrant
// satisfy it). xref -> fan tree (onViewTree); fid -> FamilySearch.
export interface PersonRef {
  place?: string | null;
  name: string;
  xref: string;
  fid: string | null;
  year?: number | null;
  nat?: string;
  gen?: number | null;
  color?: string;
  ai?: Person["ai"];
}

export interface Collapse {
  n_collapse: number;
  n_over_attached: number;
  couples: CollapseCouple[];
}

export interface DnaPerson {
  name: string;
  surname: string;
  year: number | null;
  gen: number | null;
  fid: string | null;
  xref: string | null;
  nat: string | null;
  color: string;
}

export interface Dna {
  y_line: DnaPerson[];
  mt_line: DnaPerson[];
  y_origin: string | null;
  mt_origin: string | null;
}

export interface ImmRow {
  decade: number;
  nat: string;
  count: number;
  color: string;
}

export interface Immigration {
  by_decade: ImmRow[];
  undated: number;
  total: number;
}

export interface LifeRow {
  label: string;
  median: number;
  n: number;
  color?: string;
}

export interface Longevity {
  n: number;
  by_century: LifeRow[];
  by_origin: LifeRow[];
}

export interface Stats {
  completeness: Completeness[];
  surnames: SurnameRow[];
  collapse: Collapse;
  dna: Dna;
  immigration: Immigration;
  longevity: Longevity;
}

export interface MapPayload {
  meta: TreeMeta;
  colors: Colors;
  models: Models;
  people: Person[];
  arcs: Arc[];
  immigrants: Immigrant[];
  ranges: Ranges;
  nat_counts: Record<string, number>;
  state_counts: Record<string, number>;
  immigrant_count: number;
  country_data: Record<string, CountryDatum>;
  country_details: Record<string, CountryDetail>;
  sankey: SankeyData;
  stats: Stats;
}

export interface FanRec {
  n: string;
  g: string;
  s: string; // sex ("M"/"F")
  y: number | null;
  dy: number | null;
  p: string;
  nat: string;
  c: string;
  fid: string | null;
  fa: string | null;
  mo: string | null;
  gen: number | null;
  br: string; // branch ("P"/"M") — for the fan filter dimming
  dna: string; // "Y"/"mt"
  st: string; // US state of birth ("" unless American-born) — for the state filter dimming
  // Present only on dead-end wedges whose origin isn't documented: the estimated
  // origin (place + surname + relatives), clearly an estimate, never a fact.
  est?: OriginEstimate;
  ai?: 1; // present when `nat` came from the AI place reading (see Person.ai)
}

export interface FanPayload {
  meta: TreeMeta;
  root: string | null;
  colors: Colors;
  recs: Record<string, FanRec>;
}

// Confidence in an inferred (non-documented) value. "none" = couldn't even guess.
export type Confidence = "high" | "medium" | "low" | "none";

// An ESTIMATED origin, never a documented fact. Always rendered with the
// "guess" visual language so it can't be mistaken for FamilySearch data.
export interface LikelyOrigin {
  label: string;
  pct: number;
  confidence: Confidence;
  rationale: string;
}

// One contributing signal behind a combined estimate (the verdict's "why").
export interface OriginSignal {
  basis: string; // "place" | "surname" | "relatives"
  label: string;
  confidence: Confidence;
  why: string;
}

// The reconciled verdict across all signals (place + surname + relatives).
// `agreement` is true when independent signals corroborate -- the only path to
// "high" confidence. `rationale` lists each contributing signal.
export interface OriginEstimate {
  label: string;
  confidence: Confidence;
  agreement: boolean;
  rationale: OriginSignal[];
}

// Records FamilySearch likely holds twice (AI judgment from core/duplicates.py).
export interface DupRecord {
  name: string;
  xref: string;
  fid: string | null;
  year: number | null;
  gen: number | null;
  place: string | null;
}

export interface DupGroup {
  score: number; // 0 different .. 2 same person
  shared_child: boolean; // a child claims more than one of these records as a parent
  records: DupRecord[];
}

export interface DupPair extends DupGroup {
  parents: number; // P(same parents), spelling variants allowed
  place: number; // P(same birthplace)
}

export interface DuplicatesPayload {
  n_same: number;
  n_same_records: number;
  n_possible: number;
  same: DupGroup[];
  possible: DupPair[];
}

export interface DeadendsPayload {
  meta: TreeMeta;
  wall_generation: number;
  untraced_pct: number;
  wall_pct: number;
  genuine_pct: number;
  by_reason: Record<string, number>;
  by_generation: Record<string, number>;
  top_genuine: {
    name: string;
    xref: string;
    fid: string | null;
    gen: number | null;
    place: string | null;
    reason: string;
    pct: number;
    // Estimates, NOT documented for this person. Three independent signals,
    // shown separately (combining them is a later phase): `likely_origin` from
    // the dead-end's place (colony priors), `surname_origin` from the surname's
    // etymology, `tree_origin` from same-surname relatives' documented origins.
    likely_origin: string;
    confidence: Confidence;
    rationale: string;
    surname_origin: string;
    surname_confidence: Confidence;
    surname_rationale: string;
    tree_origin: string;
    tree_confidence: Confidence;
    tree_rationale: string;
    // The reconciled verdict the UI shows (the three signals above are its "why").
    origin_estimate: OriginEstimate;
  }[];
  // Estimated origins of the untraced slice (aggregate), and the share of
  // untraced weight at each confidence level. Inferred, not documented.
  likely_origin: LikelyOrigin[];
  likely_origin_by_confidence: Record<string, number>;
}
