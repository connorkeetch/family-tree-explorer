import { useMemo, useRef, useState } from "react";
import type { PersonRef } from "../api/types";
import { formatYear } from "../lib/year";
import { AiMark } from "./AiOrigin";
import { useFocusTrap } from "../lib/useFocusTrap";

// A person's FamilySearch profile (matches the map pin + fan chart deep link).
const FS_URL = "https://www.familysearch.org/tree/person/details/";
// Cap rendered rows so a click on a huge bucket (e.g. a deep generation) stays
// snappy; the search box narrows beyond the cap.
const CAP = 400;

/**
 * The "people behind this number" panel. Opened by clicking an insight element
 * (a surname bar, a decade, a generation…); lists every person in that set with
 * a link to re-center the family-tree fan chart on them and a FamilySearch link.
 * Reuses the shared `.modal` shell (same as CountryModal). Closes on backdrop
 * click, ✕, or Escape.
 */
export default function PersonDrawer({
  title,
  people,
  onClose,
  onViewTree,
  onOpenPerson,
  hidden = false,
  searchable = people.length > 12,
}: {
  title: string;
  people: PersonRef[];
  onClose: () => void;
  onViewTree: (xref: string) => void;
  // When provided, a person's name becomes a button that opens their full
  // person page (layered over this list). Omit to keep names as plain text.
  onOpenPerson?: (xref: string) => void;
  hidden?: boolean;
  searchable?: boolean;
}) {
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, onClose, !hidden);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return needle ? people.filter((p) => p.name.toLowerCase().includes(needle) ||
      p.place?.toLowerCase().includes(needle)) : people;
  }, [people, q]);
  const shown = filtered.slice(0, CAP);

  return (
    <div className="modal-backdrop" hidden={hidden} style={hidden ? { display: "none" } : undefined} onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="modal-close" aria-label="Close" onClick={onClose}>
          ×
        </button>
        <h2 className="modal-title">{title}</h2>
        <div className="sub">
          {people.length.toLocaleString()} {people.length === 1 ? "person" : "people"}
        </div>

        {searchable && (
          <input
            type="text"
            className="drill-search"
            placeholder="Search people or places…"
            aria-label="Search people or places"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            autoFocus
          />
        )}

        <div className="drill-list">
          {shown.map((p) => (
            <div className="drill-row" key={p.xref}>
              <span className="drill-name">
                {p.color && (
                  <span className="sw" style={{ background: p.color, width: 9, height: 9 }} />
                )}
                {onOpenPerson ? (
                  <button
                    className="link-btn"
                    onClick={() => onOpenPerson(p.xref)}
                    title="Open full details"
                  >
                    {p.name}
                  </button>
                ) : (
                  p.name
                )}
                <span className="cnt">
                  {p.year ? ` · b.${formatYear(p.year)}` : ""}
                  {p.gen != null ? ` · gen ${p.gen}` : ""}
                  {p.nat ? ` · ${p.nat}` : ""}
                  <AiMark ai={p.ai} />
                </span>
                {p.place && <span className="sub" style={{ display: "block" }}>Birthplace: {p.place}</span>}
              </span>
              <span className="drill-actions">
                <button
                  className="btn"
                  onClick={() => onViewTree(p.xref)}
                  title="Center the family-tree fan chart on this person"
                >
                  Tree
                </button>
                {p.fid && (
                  <a
                    className="btn"
                    href={FS_URL + p.fid}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="Open on FamilySearch"
                  >
                    FS ↗
                  </a>
                )}
              </span>
            </div>
          ))}
          {!shown.length && <div className="sub">no matches</div>}
        </div>

        {filtered.length > CAP && (
          <div className="sub" style={{ marginTop: 8 }}>
            Showing first {CAP.toLocaleString()} of {filtered.length.toLocaleString()} — type to narrow.
          </div>
        )}
      </div>
    </div>
  );
}
