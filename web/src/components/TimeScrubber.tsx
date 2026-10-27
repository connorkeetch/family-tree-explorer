import type { Ranges } from "../api/types";
import { formatDecade } from "../lib/year";

export type ScrubMode = "off" | "born" | "alive";

export default function TimeScrubber({
  ranges,
  mode,
  setMode,
  decade,
  setDecade,
  playing,
  setPlaying,
  shown,
}: {
  ranges: Ranges;
  mode: ScrubMode;
  setMode: (m: ScrubMode) => void;
  decade: number;
  setDecade: (d: number) => void;
  playing: boolean;
  setPlaying: (p: boolean) => void;
  shown: number;
}) {
  if (!ranges.has_years) return null;
  return (
    <div className="scrubber">
      <select
        value={mode}
        onChange={(e) => setMode(e.target.value as ScrubMode)}
        style={{ width: "auto" }}
        title="Animate pins by time"
      >
        <option value="off">🕑 Time: off</option>
        <option value="born">Born by decade (fill up)</option>
        <option value="alive">Alive in decade</option>
      </select>

      {mode !== "off" && (
        <>
          <button
            onClick={() => setPlaying(!playing)}
            style={{ padding: "5px 10px" }}
            title={playing ? "Pause" : "Play"}
          >
            {playing ? "❚❚" : "▶"}
          </button>
          <input
            type="range"
            min={ranges.dec_lo}
            max={ranges.dec_hi}
            step={10}
            value={decade}
            onChange={(e) => {
              setDecade(+e.target.value);
              setPlaying(false);
            }}
            style={{ flex: 1, accentColor: "var(--accent)" }}
          />
          <span className="cnt" style={{ minWidth: 130, textAlign: "right" }}>
            {formatDecade(decade)} · {shown.toLocaleString()} shown
          </span>
        </>
      )}
    </div>
  );
}
