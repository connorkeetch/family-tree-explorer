import type { Person } from "../api/types";

const WHY =
  "The birthplace name didn't match our place rules, so an AI model (Jev) read it and " +
  "named the present-day country. It isn't a FamilySearch fact.";

/**
 * Marks an origin that came from the AI place reading, in the shared amber
 * "guess" language. `used` (high confidence) = the country shown and counted;
 * otherwise a display-only "likely X" guess that isn't counted anywhere.
 */
export default function AiOrigin({ ai }: { ai?: Person["ai"] }) {
  if (!ai) return null;
  return (
    <span className="guess-badge" title={WHY}>
      ≈ {ai.used ? "AI-mapped place" : `likely ${ai.label}`}
      <span className="conf">{Math.round(ai.conf * 100)}%</span>
    </span>
  );
}

/** Inline "≈" after a country name in compact lists and map popups. */
export function AiMark({ ai }: { ai?: Person["ai"] }) {
  if (!ai?.used) return null;
  return (
    <span className="ai-mark" title={WHY}>
      {" "}≈
    </span>
  );
}
