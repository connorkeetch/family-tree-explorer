import { useState } from "react";

/**
 * On-map legend. The map carries two distinct color encodings — pins are tinted
 * by ancestral origin, the country shading is a headcount heat ramp — and nothing
 * else on the map explains either. Collapsible so it never fights the map on
 * small screens.
 */
export default function MapLegend({ origins }: { origins: { name: string; color: string }[] }) {
  const [open, setOpen] = useState(true);
  if (!origins.length) return null;

  return (
    <div className={"maplegend" + (open ? "" : " closed")}>
      <button className="maplegend-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        Legend {open ? "▾" : "▸"}
      </button>
      {open && (
        <div className="maplegend-body">
          <div className="maplegend-head">Pins · origin</div>
          {origins.map((o) => (
            <div className="maplegend-row" key={o.name}>
              <span className="sw" style={{ background: o.color }} />
              <span className="maplegend-name">{o.name}</span>
            </div>
          ))}
          <div className="maplegend-head" style={{ marginTop: 8 }}>
            Shading · ancestors born
          </div>
          <div className="maplegend-ramp">
            <span className="maplegend-ramp-bar" />
            <span className="maplegend-ramp-lbl">
              <span>few</span>
              <span>many</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
