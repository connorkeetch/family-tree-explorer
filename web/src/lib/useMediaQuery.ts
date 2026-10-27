import { useEffect, useState } from "react";

/**
 * Subscribe to a CSS media query. Used to drive the few JS-side responsive
 * decisions that CSS can't make on its own (e.g. not applying the persisted
 * sidebar pixel-width as an inline style once the layout stacks on mobile).
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches,
  );
  useEffect(() => {
    const m = window.matchMedia(query);
    const onChange = () => setMatches(m.matches);
    onChange();
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

// Shared breakpoint: below this the dashboard stacks and the nav collapses.
export const NARROW = "(max-width: 820px)";
