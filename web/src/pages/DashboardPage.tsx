import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { MapPayload, FanPayload, DeadendsPayload, DuplicatesPayload, Person } from "../api/types";
import { AMERICAN, FilterState, defaultFilter, matchFilter } from "../lib/filter";
import { deriveInsights, deriveSankey, deriveGenComposition, sankeyMembers } from "../lib/insights";
import { useMediaQuery, NARROW } from "../lib/useMediaQuery";
import OriginsMap from "../viz/OriginsMap";
import FanChart from "../viz/FanChart";
import Sankey from "../viz/Sankey";
import StatsPanel from "../viz/StatsPanel";
import OriginBars from "../viz/OriginBars";
import StateBreakdown from "../viz/StateBreakdown";
import MapLegend from "../components/MapLegend";
import Skeleton from "../components/Skeleton";
import Filters from "../components/Filters";
import TopNav from "../components/TopNav";
import CountryModal from "../components/CountryModal";
import PersonDrawer from "../components/PersonDrawer";
import PersonModal from "../components/PersonModal";
import TimeScrubber, { ScrubMode } from "../components/TimeScrubber";

type Tab = "map" | "fan" | "migration" | "insights";
const TABS: Tab[] = ["map", "fan", "migration", "insights"];

const SIDE_KEY = "ft_dash_side_w";
const SIDE_DEFAULT = 480;
const SIDE_MIN = 300;

export default function DashboardPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const narrow = useMediaQuery(NARROW);

  // Each analysis endpoint loads independently so one slow/failed view never
  // blanks the others: the map (which also drives the sidebar + migration +
  // insights stats) is the only one the shell waits on; the fan and dead-ends
  // resolve into their own tabs with per-view loading/error.
  const [map, setMap] = useState<MapPayload | null>(null);
  const [mapErr, setMapErr] = useState<string | null>(null);
  const [fan, setFan] = useState<FanPayload | null>(null);
  const [fanErr, setFanErr] = useState<string | null>(null);
  const [deadends, setDeadends] = useState<DeadendsPayload | null>(null);
  const [deadendsErr, setDeadendsErr] = useState<string | null>(null);
  const [dups, setDups] = useState<DuplicatesPayload | null>(null);

  const [filter, setFilter] = useState<FilterState | null>(null);
  const [showArcs, setShowArcs] = useState(true);
  const [pinMode, setPinMode] = useState<"birth" | "death">("birth");
  const [fanFocus, setFanFocus] = useState<{ xref: string } | null>(null);
  // Migration drill: a clicked Sankey node/ribbon -> the people behind it.
  const [migSel, setMigSel] = useState<{ origin?: string; settlement?: string } | null>(null);
  // The person page (full detail + lineage). Layers over the migration drill when
  // opened from it; standalone otherwise (map pin, fan chart).
  const [personXref, setPersonXref] = useState<string | null>(null);
  // time-scrubber state
  const [scrubMode, setScrubMode] = useState<ScrubMode>("off");
  const [decade, setDecade] = useState(0);
  const [playing, setPlaying] = useState(false);

  // --- URL-driven view state (tab + open country modal) ---------------------
  // Keeping these in the query string makes the dashboard refresh-safe, Back-
  // button friendly, and shareable: ?tab=insights deep-links a section, and an
  // open country modal is its own history entry, so Back closes it.
  const raw = params.get("tab");
  const tab: Tab = (TABS as string[]).includes(raw || "") ? (raw as Tab) : "map";
  const countryIso = params.get("country");
  // Country display names come from the map's geojson at click time; remember
  // them so a Back/forward that re-opens the modal still has a title.
  const countryNames = useRef<Record<string, string>>({});

  const selectTab = useCallback(
    (k: Tab) => {
      if (k === "fan") setFanFocus(null); // manual entry starts at the root, not a stale pin
      // The person page + migration drill are overlays rendered outside any tab,
      // so dismiss them on a nav switch (same reason `country` is dropped below).
      setMigSel(null);
      setPersonXref(null);
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("tab", k);
          next.delete("country"); // the modal belongs to the map tab only
          return next;
        },
        { replace: false },
      );
    },
    [setParams],
  );

  // resizable sidebar (persisted); width drives the flex split with the map.
  // Skipped on narrow screens, where the sidebar stacks full-width above the map.
  const [sideW, setSideW] = useState<number>(() => {
    const v = parseInt(localStorage.getItem(SIDE_KEY) || "", 10);
    return Number.isNaN(v) ? SIDE_DEFAULT : v;
  });
  const dashRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const raf = useRef(0);

  const clampW = useCallback(
    (w: number) => Math.max(SIDE_MIN, Math.min(Math.round(window.innerWidth * 0.6), w)),
    [],
  );

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const left = dashRef.current?.getBoundingClientRect().left ?? 0;
      const w = clampW(e.clientX - left);
      if (raf.current) return;
      raf.current = requestAnimationFrame(() => {
        raf.current = 0;
        setSideW(w);
        // Leaflet listens to window resize -> re-measures the map as it shrinks/grows.
        window.dispatchEvent(new Event("resize"));
      });
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      setSideW((w) => {
        localStorage.setItem(SIDE_KEY, String(w));
        return w;
      });
      window.dispatchEvent(new Event("resize"));
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
  }, [clampW]);

  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
  };
  const resetW = () => {
    setSideW(SIDE_DEFAULT);
    localStorage.setItem(SIDE_KEY, String(SIDE_DEFAULT));
    window.dispatchEvent(new Event("resize"));
  };

  useEffect(() => {
    if (!id) return;
    let alive = true;
    setMap(null);
    setFan(null);
    setDeadends(null);
    setDups(null);
    setMapErr(null);
    setFanErr(null);
    setDeadendsErr(null);

    const onAuthFail = (e: unknown): boolean => {
      if ((e as { status?: number }).status === 401) {
        navigate("/login");
        return true;
      }
      return false;
    };
    const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

    api
      .map(id)
      .then((m) => {
        if (!alive) return;
        setMap(m);
        setFilter(defaultFilter(m.ranges));
        setDecade(m.ranges.dec_hi);
      })
      .catch((e) => {
        if (!alive || onAuthFail(e)) return;
        setMapErr(msg(e));
      });
    api
      .fan(id)
      .then((f) => alive && setFan(f))
      .catch((e) => {
        if (!alive || onAuthFail(e)) return;
        setFanErr(msg(e));
      });
    api
      .deadends(id)
      .then((d) => alive && setDeadends(d))
      .catch((e) => {
        if (!alive || onAuthFail(e)) return;
        setDeadendsErr(msg(e));
      });
    // Optional card: a failure just leaves it hidden.
    api
      .duplicates(id)
      .then((d) => alive && setDups(d))
      .catch(() => {});

    return () => {
      alive = false;
    };
  }, [id, navigate]);

  // Time-scrubber playback: advance the decade until the latest, then stop.
  useEffect(() => {
    if (!playing || scrubMode === "off" || !map) return;
    const hi = map.ranges.dec_hi;
    const timer = setInterval(() => {
      setDecade((d) => {
        if (d >= hi) {
          setPlaying(false);
          return d;
        }
        return d + 10;
      });
    }, 650);
    return () => clearInterval(timer);
  }, [playing, scrubMode, map]);

  // Stable callbacks so the (memoized) map can bail out of re-rendering when these
  // are passed down: clicking a country or jumping to the tree must not rebuild pins.
  const onCountry = useCallback(
    (iso: string, name: string) => {
      countryNames.current[iso] = name;
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("country", iso);
          return next;
        },
        { replace: false },
      );
    },
    [setParams],
  );
  const closeCountry = useCallback(() => {
    // Drop the country param in place (✕ / Esc / backdrop). Browser Back also
    // closes the modal on its own, because opening it pushed a history entry —
    // so we don't navigate(-1) here (that could overshoot on a cold-loaded link).
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("country");
        return next;
      },
      { replace: true },
    );
  }, [setParams]);
  const viewInTree = useCallback(
    (xref: string) => {
      setFanFocus({ xref });
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("tab", "fan");
          next.delete("country");
          return next;
        },
        { replace: false },
      );
    },
    [setParams],
  );
  // Open the full person page for anyone clicked across the app.
  const openPerson = useCallback((xref: string) => setPersonXref(xref), []);
  // "Open in fan chart" from a top-level modal: jump to the fan AND dismiss the
  // modal/drawer, which (unlike the tab-scoped StatsPanel drawer) won't unmount
  // on the tab switch on its own.
  const openTree = useCallback(
    (xref: string) => {
      setMigSel(null);
      setPersonXref(null);
      viewInTree(xref);
    },
    [viewInTree],
  );

  // One filtered person set drives every view -- the map pins, the selection bars,
  // the insights cards, and the migration flows all derive from it, so one control
  // (incl. the generation range) narrows everything at once. Memoized for stable
  // array identity: OriginsMap's React.memo keeps skipping marker rebuilds on
  // unrelated re-renders (modal open, sidebar drag, scrubber).
  const fpeople = useMemo(
    () => (map && filter ? map.people.filter((p) => matchFilter(filter, p)) : []),
    [map, filter],
  );
  // Map pins: filtered people that have the ACTIVE coordinate (birth or death).
  const fpts = useMemo(
    () => fpeople.filter((p) => (pinMode === "birth" ? p.lat != null : p.dlat != null)),
    [fpeople, pinMode],
  );
  // "Current selection" population: the direct line within the filter.
  const fpop = useMemo(() => fpeople.filter((p) => p.dir && p.gen !== 0), [fpeople]);
  const farcs = useMemo(
    () => (map && filter ? map.arcs.filter((a) => matchFilter(filter, a)) : []),
    [map, filter],
  );
  const fimm = useMemo(
    () => (map && filter ? map.immigrants.filter((im) => matchFilter(filter, im)) : []),
    [map, filter],
  );
  // Insights cards + migration Sankey, derived client-side from the filtered set so
  // they track the filter instantly (web/src/lib/insights.ts). At the default
  // filter they equal the server's precomputed stats/sankey block.
  const insights = useMemo(
    () => (map ? deriveInsights(fpeople, fimm, map.colors) : null),
    [map, fpeople, fimm],
  );
  const sankey = useMemo(() => (map ? deriveSankey(fimm, map.colors) : null), [map, fimm]);

  // xref -> the canonical (rich) person record, for the person page lookup.
  const peopleByXref = useMemo(() => {
    const m: Record<string, Person> = {};
    map?.people.forEach((p) => (m[p.xref] = p));
    return m;
  }, [map]);
  // People behind a clicked Sankey node/ribbon, resolved through the same fold as
  // the chart (so "Other origins"/"Other states" rollups return real people) and
  // off the filtered immigrant set (so it tracks the active filter). Deduped by
  // xref: under pedigree collapse one ancestor can immigrate on several lines.
  const migPeople = useMemo(() => {
    if (!migSel) return null;
    const seen = new Set<string>();
    return sankeyMembers(fimm, migSel).filter((im) =>
      seen.has(im.xref) ? false : (seen.add(im.xref), true),
    );
  }, [fimm, migSel]);

  // Pedigree collapse + DNA lines are whole-tree graph walks the client can't
  // recompute, so they stay server-precomputed -- we only generation-cap them.
  const inGen = useCallback(
    (g: number | null) => !filter || g == null || (g >= filter.genMin && g <= filter.genMax),
    [filter],
  );
  const collapse = useMemo(
    () =>
      map
        ? { ...map.stats.collapse, couples: map.stats.collapse.couples.filter((c) => inGen(c.gen)) }
        : null,
    [map, inGen],
  );
  const dna = useMemo(
    () =>
      map
        ? {
            ...map.stats.dna,
            y_line: map.stats.dna.y_line.filter((r) => inGen(r.gen)),
            mt_line: map.stats.dna.mt_line.filter((r) => inGen(r.gen)),
          }
        : null,
    [map, inGen],
  );
  const popTotal = useMemo(
    () => (map ? map.people.filter((p) => p.dir && p.gen !== 0).length : 0),
    [map],
  );

  const scrubbedPts = useMemo(() => {
    if (scrubMode === "off") return fpts;
    return fpts.filter((p) => {
      if (p.year == null) return false;
      if (scrubMode === "born") return Math.floor(p.year / 10) * 10 <= decade;
      // "alive": born by the end of this decade and not yet dead at its start
      if (p.year > decade + 9) return false;
      if (p.age == null) return true; // no recorded death -> assume still present
      return p.year + p.age >= decade;
    });
  }, [fpts, scrubMode, decade]);

  // Current-selection origin mix: bar width + label show the percentage of the
  // selected direct line, with the raw headcount alongside (both, per request).
  const liveBars = useMemo(() => {
    const liveCount: Record<string, number> = {};
    fpop.forEach((p) => (liveCount[p.nat] = (liveCount[p.nat] || 0) + 1));
    const total = fpop.length || 1;
    return Object.entries(liveCount)
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({
        name,
        value: (100 * count) / total,
        count,
        color: map?.colors[name] || "#888",
      }));
  }, [fpop, map]);
  // Per-generation ancestry composition for the fan side panel — whole-tree
  // (unfiltered), so empty/untraced slots read as "unknown" rather than as
  // "filtered out".
  const genComposition = useMemo(
    () => (fan ? deriveGenComposition(fan.recs, fan.root, fan.colors) : []),
    [fan],
  );
  const immBars = useMemo(
    () =>
      map
        ? map.models.immigrant.breakdown.map((b) => ({
            name: b.name,
            value: b.pct,
            color: map.colors[b.name] || "#888",
          }))
        : [],
    [map],
  );
  const countries = useMemo(
    () => (map ? Object.entries(map.nat_counts).map(([name, count]) => ({ name, count })) : []),
    [map],
  );
  // Stable, full-tree list for the "State of birth" dropdown (mirrors `countries`).
  const states = useMemo(
    () => (map ? Object.entries(map.state_counts).map(([name, count]) => ({ name, count })) : []),
    [map],
  );
  // "By U.S. state" breakdown, shown when American (USA) is the selected country.
  // Derived from the people matching every filter EXCEPT state, so picking one
  // state doesn't collapse the list — every state stays visible and clickable
  // (the bars double as the state picker). % is out of the full American direct
  // total, with the unmatched remainder surfaced as an explicit unknown bucket.
  const stateBreakdown = useMemo(() => {
    if (!map || !filter || filter.country !== AMERICAN) return null;
    const exceptState = { ...filter, state: "all" };
    const byState: Record<string, number> = {};
    let total = 0;
    for (const p of map.people) {
      if (!p.dir || p.gen === 0 || !matchFilter(exceptState, p)) continue;
      total++;
      if (p.st) byState[p.st] = (byState[p.st] || 0) + 1;
    }
    const rows = Object.entries(byState)
      .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
      .map(([name, count]) => ({ name, count, pct: total ? (100 * count) / total : 0 }));
    const known = rows.reduce((s, r) => s + r.count, 0);
    return { rows, unknown: total - known, total };
  }, [map, filter]);
  // Top origins (by mapped headcount) for the on-map legend.
  const legendItems = useMemo(() => {
    if (!map) return [];
    const tally: Record<string, number> = {};
    map.people.forEach((p) => {
      if (p.lat != null) tally[p.nat] = (tally[p.nat] || 0) + 1;
    });
    return Object.entries(tally)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name]) => ({ name, color: map.colors[name] || "#888" }));
  }, [map]);

  if (mapErr)
    return (
      <div className="center">
        <div className="err">{mapErr}</div>
        <p style={{ marginTop: 16 }}>
          <Link to="/upload">← Try another file</Link> · <Link to="/">Your trees</Link>
        </p>
      </div>
    );
  if (!map || !filter)
    return (
      <div className="app">
        <nav className="topnav">
          <span className="navbrand">
            <span className="navbrand-mark">🌳</span>
            <span className="navbrand-text">Family tree</span>
          </span>
        </nav>
        <div className={"dash" + (narrow ? " stacked" : "")}>
          <div className="side" style={narrow ? undefined : { width: sideW }}>
            <Skeleton w="55%" h={22} style={{ marginBottom: 16 }} />
            <div className="kpis">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} w={92} h={50} r={8} />
              ))}
            </div>
            <Skeleton w="45%" h={12} style={{ margin: "20px 0 10px" }} />
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} h={12} style={{ margin: "9px 0" }} />
            ))}
          </div>
          <div className="main">
            <div className="loading" style={{ textAlign: "center" }}>
              Loading analysis…
            </div>
          </div>
        </div>
      </div>
    );

  const changeScrubMode = (m: ScrubMode) => {
    setScrubMode(m);
    setPlaying(false);
    if (m !== "off") setDecade(map.ranges.dec_lo);
  };

  const navItems = [
    { key: "map", label: "🗺 Map" },
    { key: "fan", label: "🌀 Fan chart" },
    { key: "migration", label: "↗ Migration" },
    { key: "insights", label: "📊 Insights" },
  ];

  const activeDetail = countryIso ? map.country_details[countryIso] : undefined;
  const activeName = countryIso ? countryNames.current[countryIso] || countryIso : "";
  const hasCoords = map.meta.n_coords > 0;

  // Person page + migration drill (rendered at the dashboard root, over any tab).
  const activePerson = personXref ? peopleByXref[personXref] : undefined;
  const migTitle = !migSel
    ? ""
    : migSel.origin && migSel.settlement
      ? `${migSel.origin} → ${migSel.settlement}`
      : migSel.origin
        ? `Immigrants from ${migSel.origin}`
        : `Immigrants who settled in ${migSel.settlement}`;

  return (
    <div className="app">
      <TopNav
        items={navItems}
        active={tab}
        onSelect={(k) => selectTab(k as Tab)}
        rootName={map.meta.root}
      />
      <div className={"dash" + (narrow ? " stacked" : "")} ref={dashRef}>
        <div className="side" style={narrow ? undefined : { width: sideW }}>
          <h1>{map.meta.root}</h1>
          <div className="kpis">
            <div className="kpi">
              <b>{map.meta.n_direct.toLocaleString()}</b>
              <span>direct ancestors</span>
            </div>
            <div className="kpi">
              <b>{map.meta.max_gen}</b>
              <span>generations</span>
            </div>
            <div className="kpi">
              <b>{map.immigrant_count.toLocaleString()}</b>
              <span>immigrants</span>
            </div>
            <div className="kpi">
              <b>{map.meta.n_coords.toLocaleString()}</b>
              <span>mapped</span>
            </div>
          </div>

          {map.meta.living_count > 0 && (
            <div className="sub" style={{ marginTop: 2 }}>
              🔒 {map.meta.living_count} living{" "}
              {map.meta.living_count === 1 ? "person" : "people"} · shown only to you, hidden from any
              public view
            </div>
          )}

          <h2>Origins · immigrant model</h2>
          <div className="sub">Each line followed to the first ancestor who left the Old World.</div>
          <OriginBars items={immBars} />
          {map.models.immigrant.untraced_pct != null && (
            <div className="sub" style={{ marginTop: 6 }}>
              + {map.models.immigrant.untraced_pct}% untraced (origin not yet identified)
            </div>
          )}

          {/* Filters narrow every view (map, insights, migration, fan), so they're
              always available — not just on the map tab. */}
          <h2>Filters</h2>
          <Filters
            filter={filter}
            setFilter={setFilter}
            countries={countries}
            states={states}
            ranges={map.ranges}
            onReset={() => setFilter(defaultFilter(map.ranges))}
          />

          <h2>Current selection</h2>
          <div className="sub">
            {fpop.length.toLocaleString()} of {popTotal.toLocaleString()} direct ancestors ·{" "}
            {fpts.length.toLocaleString()} map pins
          </div>
          <OriginBars items={liveBars} />

          {stateBreakdown && (
            <>
              <h2>By U.S. state</h2>
              <div className="sub">
                Where your {stateBreakdown.total.toLocaleString()} American-born direct ancestors were
                born. Click a state to filter every view to it.
              </div>
              <StateBreakdown
                rows={stateBreakdown.rows}
                unknown={stateBreakdown.unknown}
                total={stateBreakdown.total}
                selected={filter.state}
                color={map.colors[AMERICAN] || "var(--accent)"}
                onSelect={(st) => setFilter({ ...filter, state: st })}
              />
            </>
          )}
        </div>

        {!narrow && (
          <div
            className="resizer"
            onMouseDown={startDrag}
            onDoubleClick={resetW}
            title="Drag to resize · double-click to reset"
          />
        )}

        <div className="main">
          {tab === "map" && (
            <div className="stagebar">
              <span className="sub" style={{ display: "flex", alignItems: "center", gap: 6, margin: 0 }}>
                Pins:
                {(["birth", "death"] as const).map((m) => (
                  <button
                    key={m}
                    className={pinMode === m ? "btn-primary" : ""}
                    style={{ padding: "3px 9px" }}
                    onClick={() => setPinMode(m)}
                  >
                    {m === "birth" ? "Birthplace" : "Place of death"}
                  </button>
                ))}
              </span>
              <label className="sub" style={{ display: "flex", alignItems: "center", gap: 6, margin: 0 }}>
                <input type="checkbox" checked={showArcs} onChange={(e) => setShowArcs(e.target.checked)} />
                migration arcs
              </label>
              <span className="sub" style={{ margin: 0 }}>
                {pinMode === "birth"
                  ? "Pins mark birthplaces. Click a shaded country for its full detail."
                  : "Pins mark places of death (origin colors retained)."}
              </span>
            </div>
          )}
          <div className={"stage stage-" + tab}>
            {tab === "map" &&
              (hasCoords ? (
                <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
                  <TimeScrubber
                    ranges={map.ranges}
                    mode={scrubMode}
                    setMode={changeScrubMode}
                    decade={decade}
                    setDecade={setDecade}
                    playing={playing}
                    setPlaying={setPlaying}
                    shown={scrubbedPts.length}
                  />
                  <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
                    <OriginsMap
                      points={scrubbedPts}
                      arcs={farcs}
                      showArcs={showArcs}
                      coordMode={pinMode}
                      countryData={map.country_data}
                      countryDetails={map.country_details}
                      onCountry={onCountry}
                      onViewTree={viewInTree}
                      onPerson={openPerson}
                    />
                    <MapLegend origins={legendItems} />
                  </div>
                </div>
              ) : (
                <div className="empty-stage">
                  <div className="empty-stage-inner">
                    <div style={{ fontSize: 30, marginBottom: 8 }}>🗺</div>
                    <h2 style={{ marginTop: 0 }}>No mappable birthplaces yet</h2>
                    <p className="sub">
                      None of the {map.meta.n_direct.toLocaleString()} direct ancestors in this tree have a
                      birthplace we could resolve to coordinates. The fan chart and insights still work — or
                      try a GEDCOM with more place data.
                    </p>
                  </div>
                </div>
              ))}
            {tab === "fan" &&
              (fanErr ? (
                <TabError message={fanErr} />
              ) : !fan ? (
                <div className="loading">Loading fan chart…</div>
              ) : fan.root ? (
                <FanChart
                  recs={fan.recs}
                  root={fan.root}
                  focus={fanFocus}
                  filter={filter}
                  genComposition={genComposition}
                  onPerson={openPerson}
                />
              ) : (
                <div className="loading">No fan data for this tree.</div>
              ))}
            {tab === "migration" && (
              <div className="insights">
                <h2 style={{ marginTop: 0 }}>Migration: origin → first New-World settlement</h2>
                <div className="sub" style={{ maxWidth: 520 }}>
                  Each immigrant ancestor flows from its Old-World origin (left) to the US state/region where their
                  first American-born child was born (right). Ribbon width = number of ancestors.
                </div>
                <div className="sub">
                  {fimm.length.toLocaleString()} of {map.immigrants.length.toLocaleString()} immigrant ancestors in
                  the current filter. Click any flow or node to see the people behind it.
                </div>
                <Sankey data={sankey!} onPick={setMigSel} />
              </div>
            )}
            {tab === "insights" && (
              <StatsPanel
                insights={insights!}
                collapse={collapse!}
                dna={dna!}
                deadends={deadends}
                deadendsError={deadendsErr}
                duplicates={dups}
                people={fpeople}
                immigrants={fimm}
                onViewTree={viewInTree}
                onPerson={openPerson}
              />
            )}
          </div>
        </div>
      </div>

      {countryIso && activeDetail && (
        <CountryModal
          iso={countryIso}
          name={activeName}
          detail={activeDetail}
          datum={map.country_data[countryIso]}
          colors={map.colors}
          onClose={closeCountry}
        />
      )}

      {/* Migration drill: the people behind a clicked Sankey node/ribbon. Hidden
          (not unmounted) while a person page is layered over it. */}
      {migSel && !activePerson && migPeople && (
        <PersonDrawer
          title={migTitle}
          people={migPeople}
          onClose={() => setMigSel(null)}
          onViewTree={openTree}
          onOpenPerson={openPerson}
        />
      )}

      {/* The person page. `onBack` is present only when it opened over the
          migration drill, so ✕/Esc closes everything but ← returns to the list. */}
      {activePerson && (
        <PersonModal
          person={activePerson}
          recs={fan?.recs ?? null}
          root={fan?.root ?? null}
          colors={map.colors}
          onClose={() => {
            setPersonXref(null);
            setMigSel(null);
          }}
          onBack={migSel ? () => setPersonXref(null) : undefined}
          onViewTree={openTree}
          onOpenPerson={openPerson}
        />
      )}
    </div>
  );
}

function TabError({ message }: { message: string }) {
  return (
    <div className="insights">
      <div className="err">Couldn’t load this view: {message}</div>
    </div>
  );
}
