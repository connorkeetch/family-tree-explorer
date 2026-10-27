// Birth/death years are stored on a single signed axis: AD years are positive,
// BC years negative (parse_gedcom.extract_year: "5626 BC" -> -5626). That keeps
// the birth-year slider one continuous range — 5626 BC on the left, the present
// on the right — instead of folding the deep legendary BC line onto the AD axis.
// Anything that shows a year to a human routes through these so a -2348 never
// leaks as a bare negative.

/** -2348 -> "2348 BC", 1850 -> "1850". */
export function formatYear(y: number): string {
  return y < 0 ? `${-y} BC` : String(y);
}

/** Decade label for the time scrubber: -2340 -> "2340s BC", 1850 -> "1850s". */
export function formatDecade(d: number): string {
  return d < 0 ? `${-d}s BC` : `${d}s`;
}
