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
  omitted = 0,
}: {
  ranges: Ranges;
  mode: ScrubMode;
  setMode: (m: ScrubMode) => void;
  decade: number;
  setDecade: (d: number) => void;
  playing: boolean;
  setPlaying: (p: boolean) => void;
  shown: number;
  omitted?: number;
}) {
  if (!ranges.has_years) return null;
  return (
    <div className={`scrubber${mode === "off" ? "" : " timeline-active"}`}>
      <select
        value={mode}
        onChange={(e) => setMode(e.target.value as ScrubMode)}
        style={{ width: "auto" }}
        title="Animate pins by time"
        aria-label="Show map pins over time"
      >
        <option value="off">🕑 Time: off</option>
        <option value="born">Born by this decade</option>
        <option value="alive">Recorded lifetimes</option>
      </select>

      {mode !== "off" && (
        <>
          <button
            onClick={() => setPlaying(!playing)}
            style={{ padding: "5px 10px" }}
            title={playing ? "Pause" : "Play"}
            aria-label={playing ? "Pause timeline" : "Play timeline"}
          >
            {playing ? "❚❚" : "▶"}
          </button>
          <input
            type="range"
            aria-label="Map decade"
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
          <span className="scrub-status">
            {formatDecade(decade)} · {shown.toLocaleString()} shown
          </span>
          {omitted > 0 && <span className="scrub-note">{omitted.toLocaleString()} omitted: {mode === "alive" ? "birth or death dates unknown" : "birth dates unknown"}.</span>}
        </>
      )}
    </div>
  );
}
