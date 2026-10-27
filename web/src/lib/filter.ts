// Shared client-side filter applied to the one canonical `people` array (and to
// arcs + immigrants), so a single control narrows the map, the selection bars,
// the insights cards, and the migration flows together — see
// web/src/lib/insights.ts for the derivations that consume the filtered set.

import type { Ranges } from "../api/types";

// The nationality label for US-born ancestors (core emits exactly this string).
// The by-state dropdown + breakdown only apply when this country is selected.
export const AMERICAN = "American (USA)";

export interface FilterState {
  branch: "all" | "P" | "M";
  country: string; // "all" or a nationality label
  state: string; // "all" or a US state name (only meaningful when country is American)
  sex: "all" | "M" | "F";
  dna: "all" | "Y" | "mt";
  yrMin: number;
  yrMax: number;
  genMin: number;
  genMax: number;
}

export interface Filterable {
  br: string;
  nat: string;
  st?: string; // present on people + fan recs; absent on arcs/immigrants (foreign-born)
  sex: string;
  dna: string;
  year: number | null;
  gen: number | null;
}

export function defaultFilter(ranges: Ranges): FilterState {
  return {
    branch: "all",
    country: "all",
    state: "all",
    sex: "all",
    dna: "all",
    yrMin: ranges.yr_lo,
    yrMax: ranges.yr_hi,
    genMin: ranges.gen_lo,
    genMax: ranges.gen_hi,
  };
}

export function matchFilter(f: FilterState, r: Filterable): boolean {
  if (f.branch !== "all" && r.br !== f.branch) return false;
  if (f.country !== "all" && r.nat !== f.country) return false;
  // State is only ever set alongside country=American; immigrants/arcs (which
  // carry no `st`) are already excluded by that country check, so the undefined
  // here never wrongly drops them.
  if (f.state !== "all" && r.st !== f.state) return false;
  if (f.sex !== "all" && r.sex !== f.sex) return false;
  if (f.dna !== "all" && !(r.dna || "").includes(f.dna)) return false;
  // null year/gen pass the range (collaterals of unknown depth aren't dropped),
  // mirroring how an undated person still shows on a year-filtered map.
  if (r.year != null && (r.year < f.yrMin || r.year > f.yrMax)) return false;
  if (r.gen != null && (r.gen < f.genMin || r.gen > f.genMax)) return false;
  return true;
}

export function isFiltered(f: FilterState, ranges: Ranges): boolean {
  return (
    f.branch !== "all" ||
    f.country !== "all" ||
    f.state !== "all" ||
    f.sex !== "all" ||
    f.dna !== "all" ||
    f.yrMin !== ranges.yr_lo ||
    f.yrMax !== ranges.yr_hi ||
    f.genMin !== ranges.gen_lo ||
    f.genMax !== ranges.gen_hi
  );
}
