// Reconstruct the direct line from the root ("you") to any ancestor, using the
// fan-chart parent pointers (fa/mo). Powers the "how you're related" lineage line
// on the person page. The fan recs already encode the whole pedigree, so this is
// a pure client-side walk — no extra payload.

import type { FanRec } from "../api/types";

export interface LineageStep {
  xref: string;
  // How this person relates to the one a step closer to you (their direct-line
  // child). null only for the root row ("you").
  rel: "father" | "mother" | null;
}

/**
 * The chain of ancestors from `root` (you) down to `target`, ordered root →
 * target. Each ancestor is tagged as the father/mother of the person one step
 * closer to you, so the UI can read "your father → his mother → …".
 *
 * Returns null when `target` isn't on a traced path to the root — a collateral
 * relative, or the fan data hasn't loaded yet. Pedigree collapse can place one
 * ancestor on several lines; we return one valid path (whichever the parent
 * pointers reach first), which is enough to show "through whom".
 */
export function lineageOf(
  target: string,
  recs: Record<string, FanRec>,
  root: string,
): LineageStep[] | null {
  if (!recs[target] || !recs[root]) return null;
  if (target === root) return [{ xref: root, rel: null }];

  // Start at the selected root so an alternate claim cannot steal a parent link.
  const childOf = new Map<string, { child: string; rel: "father" | "mother" }>();
  const queue = [root];
  const reached = new Set([root]);
  for (let i = 0; i < queue.length; i++) {
    const xref = queue[i];
    if (xref === target) break;
    const r = recs[xref];
    for (const [parent, rel] of [[r.fa, "father"], [r.mo, "mother"]] as const) {
      if (!parent || !recs[parent] || reached.has(parent)) continue;
      reached.add(parent);
      childOf.set(parent, { child: xref, rel });
      queue.push(parent);
    }
  }

  // Walk from the target toward the root, one generation closer each hop. Every
  // non-root ancestor is named by its direct-line child (whose rec lists it as a
  // parent), so the chain always reaches the root; the `seen` guard is purely
  // defensive against malformed data.
  const hops: { xref: string; rel: "father" | "mother" }[] = [];
  const seen = new Set<string>([target]);
  let cur = target;
  while (cur !== root) {
    const step = childOf.get(cur);
    if (!step || seen.has(step.child)) return null;
    hops.push({ xref: cur, rel: step.rel });
    seen.add(step.child);
    cur = step.child;
  }

  // Reverse into root → target order; the root leads as "you", each ancestor
  // carries its rel to the person before it.
  const line: LineageStep[] = [{ xref: root, rel: null }];
  for (let i = hops.length - 1; i >= 0; i--) line.push({ xref: hops[i].xref, rel: hops[i].rel });
  return line;
}
