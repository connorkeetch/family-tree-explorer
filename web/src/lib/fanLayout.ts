import type { FanRec } from "../api/types";

export const FAN_POSITION_LIMIT = 4095;

interface Node {
  x: string;
  g: number;
  idx: number;
}

export function layoutFan(recs: Record<string, FanRec>, center: string, rings: number) {
  const filled: Node[] = [];
  const gaps: { g: number; idx: number }[] = [];
  let layer: Node[] = recs[center] ? [{ x: center, g: 0, idx: 0 }] : [];
  for (let g = 0; layer.length && g <= rings; g++) {
    filled.push(...layer);
    if (g === rings) break;
    const next: Node[] = [];
    const missing: { g: number; idx: number }[] = [];
    for (const nd of layer) {
      const r = recs[nd.x];
      for (const [offset, parent] of [r.fa, r.mo].entries()) {
        const pos = { g: g + 1, idx: nd.idx * 2 + offset };
        if (parent && recs[parent]) next.push({ ...pos, x: parent });
        else missing.push(pos);
      }
    }
    // Stop before a whole ring, rather than showing a misleading partial pedigree.
    if (filled.length + gaps.length + next.length + missing.length > FAN_POSITION_LIMIT) {
      return { filled, gaps, rings: g, limited: true };
    }
    gaps.push(...missing);
    layer = next;
  }
  return { filled, gaps, rings, limited: false };
}
