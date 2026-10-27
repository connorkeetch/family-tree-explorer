import type { JSX } from "react";
import type { SankeyData } from "../api/types";

// Ported from core/analyze_origins.migration_sankey_svg: origins (left) flow to
// first New-World settlement (right); ribbon width = number of immigrant ancestors.
const NODE_W = 12;
const LX = 74;
const RX = 252;
const SX = LX + NODE_W;
const TX = RX;
const GAP = 5;
const W = 344;

export default function Sankey({
  data,
  onPick,
}: {
  data: SankeyData;
  // Click a ribbon (origin + settlement), a left node (origin) or a right node
  // (settlement) to drill into the people behind it. Omit for a static chart.
  onPick?: (sel: { origin?: string; settlement?: string }) => void;
}) {
  const { flows } = data;
  if (!flows.length) return <div className="sub">No migration flows to show.</div>;

  const oTot: Record<string, number> = {};
  const sTot: Record<string, number> = {};
  const oColor: Record<string, string> = {};
  for (const f of flows) {
    oTot[f.origin] = (oTot[f.origin] || 0) + f.count;
    sTot[f.settlement] = (sTot[f.settlement] || 0) + f.count;
    oColor[f.origin] = f.color;
  }
  const total = Object.values(oTot).reduce((a, b) => a + b, 0);
  if (total <= 0) return <div className="sub">No migration flows to show.</div>;

  const byDesc = (a: [string, number], b: [string, number]) =>
    b[1] - a[1] || (a[0] < b[0] ? -1 : 1);
  const left = Object.entries(oTot).sort(byDesc);
  const right = Object.entries(sTot).sort(byDesc);
  const scale = 430 / total;

  const stack = (items: [string, number][]): [Record<string, number>, number] => {
    const pos: Record<string, number> = {};
    let y = 2;
    for (const [lbl, v] of items) {
      pos[lbl] = y;
      y += v * scale + GAP;
    }
    return [pos, y];
  };
  const [ly, leftH] = stack(left);
  const [ry, rightH] = stack(right);
  const H = Math.max(leftH, rightH) + 2;

  const rightIndex: Record<string, number> = {};
  right.forEach(([lbl], i) => (rightIndex[lbl] = i));
  const srcOff = { ...ly };
  const tgtOff = { ...ry };

  const ribbons: JSX.Element[] = [];
  for (const [lbl] of left) {
    const outs = flows
      .filter((f) => f.origin === lbl)
      .sort((a, b) => rightIndex[a.settlement] - rightIndex[b.settlement]);
    for (const f of outs) {
      const w = f.count * scale;
      const sy0 = srcOff[lbl];
      const sy1 = sy0 + w;
      srcOff[lbl] = sy1;
      const ty0 = tgtOff[f.settlement];
      const ty1 = ty0 + w;
      tgtOff[f.settlement] = ty1;
      const mx = (SX + TX) / 2;
      const d =
        `M${SX},${sy0.toFixed(1)} C${mx},${sy0.toFixed(1)} ${mx},${ty0.toFixed(1)} ${TX},${ty0.toFixed(1)} ` +
        `L${TX},${ty1.toFixed(1)} C${mx},${ty1.toFixed(1)} ${mx},${sy1.toFixed(1)} ${SX},${sy1.toFixed(1)} Z`;
      ribbons.push(
        <path
          key={`${lbl}->${f.settlement}`}
          className={onPick ? "sankey-rib" : undefined}
          d={d}
          fill={f.color}
          fillOpacity={0.4}
          style={onPick ? { cursor: "pointer" } : undefined}
          onClick={onPick ? () => onPick({ origin: lbl, settlement: f.settlement }) : undefined}
        >
          <title>
            {lbl} → {f.settlement}: {f.count}
            {onPick ? " · click for people" : ""}
          </title>
        </path>,
      );
    }
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H.toFixed(0)}`}
      width="100%"
      style={{ maxWidth: 460, display: "block" }}
      role="img"
      aria-label="Migration from origin to settlement"
    >
      {ribbons}
      {left.map(([lbl, v]) => {
        const h = Math.max(1.5, v * scale);
        return (
          <g
            key={`L-${lbl}`}
            className={onPick ? "sankey-node" : undefined}
            style={onPick ? { cursor: "pointer" } : undefined}
            onClick={onPick ? () => onPick({ origin: lbl }) : undefined}
          >
            <rect x={LX} y={ly[lbl]} width={NODE_W} height={h} fill={oColor[lbl]} rx={2}>
              <title>
                {lbl}: {v}
                {onPick ? " · click for people" : ""}
              </title>
            </rect>
            <text x={LX - 4} y={ly[lbl] + h / 2 + 3.2} textAnchor="end" className="snlbl">
              {lbl}
            </text>
          </g>
        );
      })}
      {right.map(([lbl, v]) => {
        const h = Math.max(1.5, v * scale);
        const muted = lbl.startsWith("(") || lbl.startsWith("Other");
        return (
          <g
            key={`R-${lbl}`}
            className={onPick ? "sankey-node" : undefined}
            style={onPick ? { cursor: "pointer" } : undefined}
            onClick={onPick ? () => onPick({ settlement: lbl }) : undefined}
          >
            <rect x={RX} y={ry[lbl]} width={NODE_W} height={h} fill={muted ? "#6b7280" : "#8a93a6"} rx={2}>
              <title>
                {lbl}: {v}
                {onPick ? " · click for people" : ""}
              </title>
            </rect>
            <text x={RX + NODE_W + 4} y={ry[lbl] + h / 2 + 3.2} textAnchor="start" className="snlbl">
              {lbl} <tspan className="cnt">{v}</tspan>
            </text>
          </g>
        );
      })}
    </svg>
  );
}
