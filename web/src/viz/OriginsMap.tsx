import { memo, useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import Supercluster from "supercluster";
import type { Person, Arc, CountryDatum, CountryDetail } from "../api/types";
import { formatYear } from "../lib/year";

// Bundled public-domain Natural Earth boundaries; see the GeoJSON's source field.
const GEOURL = "/world-countries.geojson";

// A person's FamilySearch profile (matches the Fan chart's deep link).
const FS_URL = "https://www.familysearch.org/tree/person/details/";

export type CoordMode = "birth" | "death";
export interface MapCamera { center: [number, number]; zoom: number; }
// Which coordinate + place + year a pin shows, per the birth/death toggle. Points
// are pre-filtered by the dashboard to those that HAVE the active coordinate.
function pin(p: Person, mode: CoordMode) {
  return mode === "death"
    ? { lat: p.dlat as number, lon: p.dlon as number, place: p.dplace, year: p.dyear ?? null, verb: "d." }
    : { lat: p.lat as number, lon: p.lon as number, place: p.place, year: p.year, verb: "b." };
}

// One DivIcon per color (pins reuse them — ~20 distinct, not 27k).
const iconCache = new Map<string, L.DivIcon>();
function dotIcon(color: string): L.DivIcon {
  let ic = iconCache.get(color);
  if (!ic) {
    ic = L.divIcon({
      className: "pin-dot",
      html: `<span style="background:${color}"></span>`,
      iconSize: [12, 12],
    });
    iconCache.set(color, ic);
  }
  return ic;
}

// Cluster bubble: size by count, tinted by the cluster's dominant origin color.
function clusterIcon(count: number, color: string): L.DivIcon {
  const size = count < 10 ? 30 : count < 100 ? 38 : count < 1000 ? 46 : 54;
  return L.divIcon({
    html: `<div class="cb" style="background:${color};width:${size}px;height:${size}px"><span>${count.toLocaleString()}</span></div>`,
    className: "cluster-bubble",
    iconSize: [size, size],
  });
}

function dominantColor(colors: Record<string, number>): string {
  let best = "#888";
  let n = -1;
  for (const c in colors) {
    if (colors[c] > n) {
      n = colors[c];
      best = c;
    }
  }
  return best;
}

function fitSelection(map: L.Map, points: Person[], coordMode: CoordMode) {
  if (!points.length) return;
  map.fitBounds(L.latLngBounds(points.map((p) => {
    const c = pin(p, coordMode); return [c.lat, c.lon] as [number, number];
  })), { padding: [30, 30], maxZoom: 8 });
}

function FitBounds({ map, points, coordMode, restored }: { map: L.Map; points: Person[]; coordMode: CoordMode; restored: boolean }) {
  const fitted = useRef(false);
  useEffect(() => {
    if (fitted.current || restored || !points.length) return;
    fitSelection(map, points, coordMode);
    fitted.current = true;
  }, [points, map, coordMode, restored]);
  return null;
}

function ramp(t: number): string | null {
  return t <= 0 ? null
    : t > 0.8 ? "#800026" : t > 0.6 ? "#BD0026" : t > 0.4 ? "#E31A1C"
    : t > 0.25 ? "#FC4E2A" : t > 0.1 ? "#FD8D3C" : "#FEB24C";
}

// Per-cluster accumulator: a tally of origin colors so the bubble can be tinted by
// the dominant one. supercluster's map() seeds it per point, reduce() merges them.
type ClusterAcc = { colors: Record<string, number> };

function personContent(p: Person, mode: CoordMode, actions?: {
  onPerson: (xref: string) => void;
  onViewTree: (xref: string) => void;
}) {
  const c = pin(p, mode);
  const when = c.year ? `${c.verb} ${formatYear(c.year)}`
    : mode === "death" ? "death year unknown" : "birth year unknown";
  const content = L.DomUtil.create("div", "pin-pop");
  L.DomUtil.create("b", "", content).textContent = p.name;
  const meta = L.DomUtil.create("div", "pin-pop-meta", content);
  meta.append(document.createTextNode(when + (p.gen != null ? ` · gen ${p.gen}` : "")),
    document.createElement("br"), document.createTextNode(c.place || "—"), document.createElement("br"));
  const origin = L.DomUtil.create("span", "", meta);
  origin.style.color = p.color;
  origin.textContent = `● ${p.nat}`;
  if (p.ai?.used) {
    const mark = L.DomUtil.create("span", "ai-mark", meta);
    mark.textContent = " ≈";
    mark.title = "AI-mapped birthplace; not a FamilySearch fact.";
  }
  if (p.imm) meta.append(document.createTextNode(" · immigrant"));
  if (actions) {
    const controls = L.DomUtil.create("div", "pin-pop-actions", content);
    if (p.xref) {
      for (const [label, act] of [["Details", actions.onPerson], ["Family tree", actions.onViewTree]] as const) {
        const button = L.DomUtil.create("button", "btn", controls);
        button.type = "button";
        button.textContent = label;
        button.onclick = () => act(p.xref);
      }
    }
    if (p.fid) {
      const link = L.DomUtil.create("a", "btn", controls);
      link.textContent = "FamilySearch ↗";
      link.href = FS_URL + encodeURIComponent(p.fid);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
  }
  return content;
}

/**
 * High-performance marker layer. supercluster indexes every point once (tens of
 * ms even at 27k); we then render only the clusters/points inside the current
 * viewport — at most a few hundred markers, never the whole set. Panning or
 * zooming re-queries the index; changing the filter (or the birth/death pin mode)
 * just re-indexes the point list at the active coordinate. Tooltips/popups bind
 * only on the handful of visible pins.
 */
function ClusteredMarkers({
  map,
  points,
  coordMode,
  onViewTree,
  onPerson,
}: {
  map: L.Map;
  points: Person[];
  coordMode: CoordMode;
  onViewTree: (xref: string) => void;
  onPerson: (xref: string) => void;
}) {
  const [view, setView] = useState<{ bbox: [number, number, number, number]; zoom: number } | null>(null);
  const actions = useRef({ onPerson, onViewTree });
  actions.current = { onPerson, onViewTree };

  const index = useMemo(() => {
    const sc = new Supercluster<Person, ClusterAcc>({
      radius: 50,
      maxZoom: 16,
      map: (p) => ({ colors: { [p.color]: 1 } }),
      reduce: (acc, props) => {
        for (const c in props.colors) acc.colors[c] = (acc.colors[c] || 0) + props.colors[c];
      },
    });
    sc.load(
      points.map((p) => {
        const c = pin(p, coordMode);
        return {
          type: "Feature",
          properties: p,
          geometry: { type: "Point", coordinates: [c.lon, c.lat] },
        };
      }) as Supercluster.PointFeature<Person>[],
    );
    return sc;
  }, [points, coordMode]);

  const layer = useMemo(() => ({
    group: L.layerGroup(),
    markers: new Map<string, L.Marker>(),
  }), [map, index]);

  useEffect(() => {
    layer.group.addTo(map);
    return () => {
      layer.group.remove();
      layer.markers.clear();
    };
  }, [map, layer]);

  // Track the viewport so we only render what's on screen, re-querying the index
  // on every pan/zoom. Longitudes are NORMALIZED to [-180, 180) rather than
  // clamped: with worldCopyJump the bounds can run past ±180 (e.g. west = 190),
  // and clamping there yields an invalid west > east box that makes supercluster
  // query the whole world (defeating the optimization) or return nothing.
  // Normalizing instead lets a genuine antimeridian crossing fall out as
  // west > east — which getClusters handles correctly. A viewport spanning the
  // whole globe (>= 360°) queries the full world directly.
  useEffect(() => {
    const update = () => {
      const b = map.getBounds();
      const west = b.getWest();
      const east = b.getEast();
      const south = Math.max(-90, b.getSouth());
      const north = Math.min(90, b.getNorth());
      const zoom = Math.round(map.getZoom());
      if (east - west >= 360) {
        setView({ bbox: [-180, south, 180, north], zoom });
      } else {
        const norm = (lng: number) => ((((lng + 180) % 360) + 360) % 360) - 180;
        setView({ bbox: [norm(west), south, norm(east), north], zoom });
      }
    };
    update();
    map.on("moveend zoomend", update);
    return () => {
      map.off("moveend zoomend", update);
    };
  }, [map]);

  useEffect(() => {
    if (!view) return;
    const visible = new Set<string>();
    for (const f of index.getClusters(view.bbox, view.zoom)) {
      const [lon, lat] = f.geometry.coordinates as [number, number];
      const cp = f.properties as Supercluster.ClusterProperties & ClusterAcc;
      const key = cp.cluster ? `cluster:${cp.cluster_id}` : `person:${(f.properties as Person).xref}`;
      visible.add(key);
      // Popup auto-pan fires moveend too. Keep its source marker attached while
      // it remains visible, or Leaflet closes the popup before its buttons work.
      if (layer.markers.has(key)) continue;
      let marker: L.Marker;
      if (cp.cluster) {
        marker = L.marker([lat, lon], { icon: clusterIcon(cp.point_count, dominantColor(cp.colors)) })
          .on("click", () => map.setView([lat, lon], Math.min(index.getClusterExpansionZoom(cp.cluster_id), 16)));
      } else {
        const p = f.properties as Person;
        marker = L.marker([lat, lon], { icon: dotIcon(p.color), title: p.name, alt: p.name })
          .bindTooltip(() => personContent(p, coordMode))
          .bindPopup(() => personContent(p, coordMode, actions.current));
      }
      marker.addTo(layer.group);
      layer.markers.set(key, marker);
    }
    for (const [key, marker] of layer.markers) {
      if (!visible.has(key)) {
        layer.group.removeLayer(marker);
        layer.markers.delete(key);
      }
    }
  }, [map, index, view, coordMode, layer]);
  return null;
}

/**
 * Static (unfiltered) choropleth of where ancestors were born, shaded by
 * `country_data` headcount. Built imperatively against the Leaflet map with an
 * explicit SVG renderer, so each country is a real path with click + hover-cursor
 * support, layered behind the clustered pins. Countries with detail data are
 * clickable and open the country modal. Reads its inputs through refs so the layer
 * is built once per mount and never re-fetches the geojson on a parent re-render.
 */
function CountryChoropleth({
  map,
  countryData,
  countryDetails,
  onCountry,
  onError,
  onNames,
}: {
  map: L.Map;
  countryData: Record<string, CountryDatum>;
  countryDetails: Record<string, CountryDetail>;
  onCountry: (iso: string, name: string) => void;
  onError?: () => void;
  onNames?: (names: Record<string, string>) => void;
}) {
  const dataRef = useRef(countryData);
  const detailRef = useRef(countryDetails);
  const onCountryRef = useRef(onCountry);
  const onErrorRef = useRef(onError);
  const namesRef = useRef(onNames);
  dataRef.current = countryData;
  detailRef.current = countryDetails;
  onCountryRef.current = onCountry;
  onErrorRef.current = onError;
  namesRef.current = onNames;

  useEffect(() => {
    let layer: L.GeoJSON | null = null;
    let cancelled = false;
    const renderer = L.svg({ padding: 0.5 });
    const data = dataRef.current;
    const max = Math.max(1, ...Object.values(data).map((d) => d.count || 0));

    fetch(GEOURL)
      .then((r) => {
        if (!r.ok) throw new Error(`Country borders: ${r.status}`);
        return r.json();
      })
      .then((gj) => {
        if (cancelled) return;
        namesRef.current?.(Object.fromEntries(gj.features.map((feature: GeoJSON.Feature) => [String(feature.id), String(feature.properties?.name || feature.id)])));
        layer = L.geoJSON(gj as GeoJSON.GeoJsonObject, {
          style: (feature) => {
            const iso = feature ? String(feature.id) : "";
            const v = data[iso]?.count || 0;
            const c = ramp(max > 0 ? v / max : 0);
            return {
              renderer, // explicit SVG path -> clickable + hover cursor
              fillColor: c || "#263042",
              fillOpacity: c ? 0.3 : 0.06,
              color: "#3a4255",
              weight: 1,
            };
          },
          onEachFeature: (feature, lyr) => {
            const iso = String(feature.id);
            const name = (feature.properties && feature.properties.name) || iso;
            const d = data[iso];
            if (d) {
              const more = detailRef.current[iso] ? "<br><i>click for country detail →</i>" : "";
              lyr.bindTooltip(
                `<b>${name}</b><br>${d.count} people born here<br>immigrant origin: ${d.immw}%${more}`,
                { sticky: true },
              );
            }
            if (detailRef.current[iso]) {
              lyr.on("click", () => onCountryRef.current(iso, name));
              lyr.on("add", () => {
                const path = (lyr as unknown as { _path?: SVGElement })._path;
                if (path) path.style.cursor = "pointer";
              });
            }
          },
        }).addTo(map);
        layer.bringToBack();
      })
      .catch((e) => {
        console.warn("Country borders failed to load:", e);
        if (!cancelled) onErrorRef.current?.();
      });

    return () => {
      cancelled = true;
      if (layer) map.removeLayer(layer);
    };
  }, [map]);

  return null;
}

function OriginsMap({
  points,
  arcs,
  showArcs,
  coordMode,
  countryData,
  countryDetails,
  onCountry,
  onViewTree,
  onPerson,
  initialCamera,
  onCameraChange,
  onCountryNames,
}: {
  points: Person[];
  arcs: Arc[];
  showArcs: boolean;
  coordMode: CoordMode;
  countryData: Record<string, CountryDatum>;
  countryDetails: Record<string, CountryDetail>;
  onCountry: (iso: string, name: string) => void;
  onViewTree: (xref: string) => void;
  onPerson: (xref: string) => void;
  initialCamera?: MapCamera;
  onCameraChange?: (camera: MapCamera) => void;
  onCountryNames?: (names: Record<string, string>) => void;
}) {
  const [bordersError, setBordersError] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<L.Map | null>(null);
  useEffect(() => {
    const created = L.map(container.current!, { worldCopyJump: true }).setView(initialCamera?.center ?? [40, -40], initialCamera?.zoom ?? 3);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> · Made with Natural Earth',
    }).addTo(created);
    setMap(created);
    const remember = () => {
      if (!onCameraChange) return;
      const center = created.getCenter();
      onCameraChange({ center: [center.lat, center.lng], zoom: created.getZoom() });
    };
    if (onCameraChange) created.on("moveend zoomend", remember);
    return () => {
      remember();
      if (onCameraChange) created.off("moveend zoomend", remember);
      created.remove();
    };
  }, []);

  // Arcs change independently of the clustered marker layer.
  useEffect(() => {
    if (!map || !showArcs) return;
    const lines = L.layerGroup(arcs.map((a) => L.polyline([a.from, a.to],
      { color: a.color, weight: 1, opacity: 0.5 }))).addTo(map);
    return () => { lines.remove(); };
  }, [map, arcs, showArcs]);

  return (
    <>
      {bordersError && (
        <div className="map-note" role="status">
          Country borders couldn’t load — pins and arcs still work, but shaded countries are hidden.
          Reload the page to try again.
        </div>
      )}
      <div ref={container} style={{ height: "100%", width: "100%" }} />
      {map && <>
        <CountryChoropleth
          map={map}
          countryData={countryData}
          countryDetails={countryDetails}
          onCountry={onCountry}
          onError={() => setBordersError(true)}
          onNames={onCountryNames}
        />

        <ClusteredMarkers
          map={map}
          points={points}
          coordMode={coordMode}
          onViewTree={onViewTree}
          onPerson={onPerson}
        />

        <FitBounds map={map} points={points} coordMode={coordMode} restored={!!initialCamera} />
        <button className="map-fit" disabled={!points.length} onClick={() => fitSelection(map, points, coordMode)}>Fit selection</button>
      </>}
    </>
  );
}

// Memoized so the map only re-renders when its own inputs change — clicking a
// country or toggling the scrubber no longer rebuilds it.
export default memo(OriginsMap);
