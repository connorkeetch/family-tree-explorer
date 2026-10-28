import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { MapPayload, FanPayload, DeadendsPayload, DuplicatesPayload, Person, PersonRef } from "../api/types";
import { AMERICAN, FilterState, defaultFilter, matchFilter, matchDecade, FILTER_KEYS, readFilter, writeFilter } from "../lib/filter";
import { deriveInsights, deriveSankey, deriveGenComposition, sankeyMembers } from "../lib/insights";
import OriginsMap, { MapCamera } from "../viz/OriginsMap";
import FanChart from "../viz/FanChart";
import Sankey from "../viz/Sankey";
import StatsPanel from "../viz/StatsPanel";
import OriginBars from "../viz/OriginBars";
import MapLegend from "../components/MapLegend";
import Filters from "../components/Filters";
import TopNav from "../components/TopNav";
import CountryModal from "../components/CountryModal";
import PersonDrawer from "../components/PersonDrawer";
import PersonModal from "../components/PersonModal";
import TimeScrubber, { ScrubMode } from "../components/TimeScrubber";
import { useFocusTrap } from "../lib/useFocusTrap";
import { formatYear } from "../lib/year";

type Tab = "map" | "fan" | "migration" | "insights";
const TABS: Tab[] = ["map", "fan", "migration", "insights"];

type PeopleList = { title: string; people: PersonRef[] };

export default function DashboardPage() {
  const { id } = useParams<{ id: string }>();
  const [params, setParams] = useSearchParams();

  // Each analysis endpoint loads independently so one slow/failed view never
  // blanks the others: the map (which also drives migration and insight stats)
  // is the only one the shell waits on; the fan and dead-ends
  // resolve into their own tabs with per-view loading/error.
  const [map, setMap] = useState<MapPayload | null>(null);
  const [mapErr, setMapErr] = useState<string | null>(null);
  const [fan, setFan] = useState<FanPayload | null>(null);
  const [fanErr, setFanErr] = useState<string | null>(null);
  const [deadends, setDeadends] = useState<DeadendsPayload | null>(null);
  const [deadendsErr, setDeadendsErr] = useState<string | null>(null);
  const [dups, setDups] = useState<DuplicatesPayload | null>(null);

  const filterKey = JSON.stringify(FILTER_KEYS.map((key) => params.get(key)));
  const filter = useMemo(() => map ? readFilter(params, map.ranges) : null, [map, filterKey]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement>(null);
  useFocusTrap(filterRef, () => setFiltersOpen(false), filtersOpen);
  const camera = useRef<MapCamera | undefined>(undefined);
  const rememberCamera = useCallback((view: MapCamera) => { camera.current = view; }, []);
  const lists = useRef(new Map<string, PeopleList>());
  const listSequence = useRef(0);
  const listId = params.get("list");
  const personXref = params.get("person");
  const focusXref = params.get("focus");
  const fanFocus = useMemo(() => focusXref ? { xref: focusXref } : null, [focusXref]);
  const applyFilters = useCallback((next: FilterState) => {
    if (map) setParams((prev) => writeFilter(prev, next, map.ranges), { replace: true });
  }, [map, setParams]);
  const [showArcs, setShowArcs] = useState(true);
  const [pinMode, setPinMode] = useState<"birth" | "death">("birth");
  // Migration drill: a clicked Sankey node/ribbon -> the people behind it.
  // The person page (full detail + lineage). Layers over the migration drill when
  // opened from it; standalone otherwise (map pin, fan chart).
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
  const [countryLabels, setCountryLabels] = useState<Record<string, string>>({});
  const rememberCountries = useCallback((names: Record<string, string>) => {
    countryNames.current = names;
    setCountryLabels(names);
  }, []);

  const selectTab = useCallback((k: Tab) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", k);
      next.delete("country"); next.delete("person"); next.delete("list");
      return next;
    });
  }, [setParams]);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    setMap(null);
    camera.current = undefined;
    lists.current.clear();
    setPlaying(false);
    setFiltersOpen(false);
    setFan(null);
    setDeadends(null);
    setDups(null);
    setMapErr(null);
    setFanErr(null);
    setDeadendsErr(null);

    const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

    api
      .map(id)
      .then((m) => {
        if (!alive) return;
        setMap(m);
        setDecade(m.ranges.dec_hi);
      })
      .catch((e) => {
        if (!alive) return;
        setMapErr(msg(e));
      });
    api
      .fan(id)
      .then((f) => alive && setFan(f))
      .catch((e) => {
        if (!alive) return;
        setFanErr(msg(e));
      });
    api
      .deadends(id)
      .then((d) => alive && setDeadends(d))
      .catch((e) => {
        if (!alive) return;
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
  }, [id]);

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
  const showPeople = useCallback((title: string, people: PersonRef[]) => {
    const key = String(++listSequence.current);
    lists.current.set(key, { title, people });
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("list", key); next.delete("person"); next.delete("country");
      return next;
    });
  }, [setParams]);
  const closeList = useCallback(() => setParams((prev) => {
    const next = new URLSearchParams(prev); next.delete("list"); next.delete("person"); return next;
  }, { replace: true }), [setParams]);
  const openPerson = useCallback((xref: string) => setParams((prev) => {
    const next = new URLSearchParams(prev); next.set("person", xref); return next;
  }), [setParams]);
  const closePerson = useCallback(() => setParams((prev) => {
    const next = new URLSearchParams(prev); next.delete("person"); return next;
  }, { replace: true }), [setParams]);
  const viewInTree = useCallback((xref: string) => setParams((prev) => {
    const next = new URLSearchParams(prev);
    next.set("tab", "fan"); next.set("focus", xref);
    next.delete("person"); next.delete("list"); next.delete("country");
    return next;
  }), [setParams]);
  const rememberFocus = useCallback((xref: string) => setParams((prev) => {
    if (prev.get("focus") === xref) return prev;
    const next = new URLSearchParams(prev); next.set("focus", xref); return next;
  }, { replace: true }), [setParams]);

  // One filtered person set drives every view -- the map pins, the selection bars,
  // the insights cards, and the migration flows all derive from it, so one control
  // (incl. the generation range) narrows everything at once. Memoized for stable
  // array identity: OriginsMap's React.memo keeps skipping marker rebuilds on
  // unrelated re-renders (modal open, scrubber).
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
  // Per-generation ancestry composition for the fan side panel — whole-tree
  // (unfiltered), so empty/untraced slots read as "unknown" rather than as
  // "filtered out".
  const genComposition = useMemo(
    () => (fan ? deriveGenComposition(fan.recs, fan.root, fan.colors) : []),
    [fan],
  );

  // Insights cards + migration Sankey, derived client-side from the filtered set so
  // they track the filter instantly (web/src/lib/insights.ts). At the default
  // filter they equal the server's precomputed stats/sankey block.
  const insights = useMemo(
    () => map ? { ...deriveInsights(fpeople, fimm, map.colors),
      completeness: genComposition.filter((g) => g.gen > 0).map((g) => ({ gen: g.gen, known: g.known, expected: g.slots })) } : null,
    [map, fpeople, fimm, genComposition],
  );
  const sankey = useMemo(() => (map ? deriveSankey(fimm, map.colors) : null), [map, fimm]);

  // xref -> the canonical (rich) person record, for the person page lookup.
  const peopleByXref = useMemo(() => {
    const m: Record<string, Person> = {};
    map?.people.forEach((p) => (m[p.xref] = p));
    return m;
  }, [map]);
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

  const scrubbedPts = useMemo(() => fpts.filter((p) => matchDecade(scrubMode, decade, p)), [fpts, scrubMode, decade]);
  const omittedDates = useMemo(() => scrubMode === "off" ? 0 : fpts.filter((p) => p.year == null ||
    (scrubMode === "alive" && (p.dyear == null || p.dyear < p.year))).length, [fpts, scrubMode]);
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
  const legendItems = useMemo(() => {
    const tally: Record<string, number> = {};
    scrubbedPts.forEach((p) => { tally[p.nat] = (tally[p.nat] || 0) + 1; });
    return Object.entries(tally).sort((a, b) => b[1] - a[1]).slice(0, 8)
      .map(([name]) => ({ name, color: map?.colors[name] || "#888" }));
  }, [map, scrubbedPts]);

  if (mapErr) return <div className="center" role="alert">
    <h1>We couldn’t load this tree</h1><p>{mapErr}</p>
    <button onClick={() => window.location.reload()}>Retry</button> <Link to="/">Your saved trees</Link>
  </div>;
  if (!map || !filter) return <div className="loading" role="status">Loading your tree…</div>;

  const defaults = defaultFilter(map.ranges);
  const chips: { label: string; clear: Partial<FilterState> }[] = [];
  if (filter.branch !== "all") chips.push({ label: filter.branch === "P" ? "Father’s side" : "Mother’s side", clear: { branch: "all" } });
  if (filter.country !== "all") chips.push({ label: filter.country, clear: { country: "all", state: "all" } });
  if (filter.state !== "all") chips.push({ label: filter.state, clear: { state: "all" } });
  if (filter.sex !== "all") chips.push({ label: filter.sex === "M" ? "Male records" : "Female records", clear: { sex: "all" } });
  if (filter.dna !== "all") chips.push({ label: filter.dna === "Y" ? "Father → father" : "Mother → mother", clear: { dna: "all" } });
  if (filter.genMin !== defaults.genMin || filter.genMax !== defaults.genMax) chips.push({ label: `Generations ${filter.genMin}–${filter.genMax}`, clear: { genMin: defaults.genMin, genMax: defaults.genMax } });
  if (filter.yrMin !== defaults.yrMin || filter.yrMax !== defaults.yrMax) chips.push({ label: `Born ${formatYear(filter.yrMin)}–${formatYear(filter.yrMax)}`, clear: { yrMin: defaults.yrMin, yrMax: defaults.yrMax } });
  const activePerson = personXref ? peopleByXref[personXref] : undefined;
  const activeList = listId ? lists.current.get(listId) : undefined;
  const unavailableList = !!listId && !activeList;
  const activeDetail = countryIso ? map.country_details[countryIso] : undefined;
  const activeName = countryIso ? countryNames.current[countryIso] || countryIso : "";
  const hasCountryData = Object.values(map.country_data).some((d) => d.count > 0);
  const modeCoordinates = map.people.filter((p) => pinMode === "birth" ? p.lat != null : p.dlat != null).length;
  const changeScrubMode = (mode: ScrubMode) => {
    setScrubMode(mode); setPlaying(false);
    if (mode !== "off") setDecade(map.ranges.dec_lo);
  };
  const migrationList = (selection: { origin?: string; settlement?: string }) => {
    const people = [...new Map(sankeyMembers(fimm, selection).map((p) => [p.xref, p])).values()];
    const title = selection.origin && selection.settlement ? `${selection.origin} → ${selection.settlement}`
      : selection.origin ? `From ${selection.origin}` : `Settled in ${selection.settlement}`;
    showPeople(title, people);
  };
  const exploreCountry = (iso: string) => showPeople(`People born in ${countryNames.current[iso] || iso} · whole tree`,
    map.people.filter((p) => p.iso === iso && p.gen !== 0));

  return <div className="app explorer">
    <TopNav items={[{ key: "map", label: "Map" }, { key: "fan", label: "Family tree" },
      { key: "migration", label: "Migration" }, { key: "insights", label: "Research" }]}
      active={tab} onSelect={(key) => selectTab(key as Tab)} />
    <div className="explorer-header">
      <div><h1>{map.meta.root || "Your tree"}</h1>
        <p className="sub">{popTotal.toLocaleString()} ancestors · {map.meta.max_gen} generations</p>
      </div>
      <div className="explorer-actions">
        <button aria-expanded={filtersOpen} aria-controls="explorer-filters" onClick={() => setFiltersOpen(true)}>Filters{chips.length ? ` (${chips.length})` : ""}</button>
        <button className="btn-primary" onClick={() => showPeople("Find a person", map.people)}>Find a person</button>
      </div>
    </div>
    {chips.length > 0 && <div className="selection-toolbar">
      <span className="selection-status" role="status">{fpop.length.toLocaleString()} of {popTotal.toLocaleString()} ancestors match</span>
      {chips.map((chip) => <button key={chip.label} className="filter-chip" aria-label={`Clear ${chip.label} filter`}
        onClick={() => applyFilters({ ...filter, ...chip.clear })}>{chip.label} ×</button>)}
      <button className="linkbtn" onClick={() => applyFilters(defaults)}>Clear all</button>
    </div>}
    {unavailableList && !activePerson && <div className="list-notice" role="status">
      This people list is no longer available after reloading or signing in. Select its country, route, or research hint again.
      <button onClick={closeList}>Dismiss</button>
      <button onClick={() => showPeople("Find a person", map.people)}>Find a person</button>
    </div>}
    <details className="ancestry-summary"><summary>Estimated family origins <span className="scope-label">Whole tree</span></summary>
      <div className="ancestry-summary-body"><OriginBars items={immBars} />
        <p className="sub">Each family line is followed to its first recorded ancestor from outside the New World. These are estimates from imported records, not DNA results. {map.models.immigrant.untraced_pct ?? 0}% of the model is unresolved. This summary stays the same when you filter.</p>
      </div>
    </details>
    <main className="explorer-main">
      {tab === "map" && <div className="stage stage-map">
        <div className="stagebar">
          <div className="pin-options" role="group" aria-label="Map locations">
            {(["birth", "death"] as const).map((mode) => <button key={mode} aria-pressed={pinMode === mode}
              className={pinMode === mode ? "selected-toggle" : ""} onClick={() => setPinMode(mode)}>{mode === "birth" ? "Birthplaces" : "Death places"}</button>)}
          </div>
          <label className="arc-toggle"><input type="checkbox" checked={showArcs} onChange={(e) => setShowArcs(e.target.checked)} /> Migration paths</label>
          <select className="country-picker" aria-label="Explore country summaries" value="" onChange={(e) => { if (e.target.value) onCountry(e.target.value, countryLabels[e.target.value] || e.target.value); }}>
            <option value="">Explore a country…</option>
            {Object.keys(map.country_details).sort((a, b) => (countryLabels[a] || a).localeCompare(countryLabels[b] || b)).map((iso) =>
              <option key={iso} value={iso}>{countryLabels[iso] || map.country_details[iso].nats.map(([n]) => n).join(" / ") || iso}</option>)}
          </select>
          {modeCoordinates > 0 && <TimeScrubber ranges={map.ranges} mode={scrubMode} setMode={changeScrubMode}
            decade={decade} setDecade={setDecade} playing={playing} setPlaying={setPlaying} shown={scrubbedPts.length} omitted={omittedDates} />}
        </div>
        <div className="map-context">Pins: matching people{scrubMode !== "off" ? " and timeline" : ""}. Country shading: whole-tree birth records.</div>
        <div className="map-surface">
          <OriginsMap points={scrubbedPts} arcs={scrubMode === "off" ? farcs : []} showArcs={showArcs} coordMode={pinMode}
            countryData={map.country_data} countryDetails={map.country_details} onCountry={onCountry}
            onViewTree={viewInTree} onPerson={openPerson} initialCamera={camera.current} onCameraChange={rememberCamera} onCountryNames={rememberCountries} />
          {scrubbedPts.length > 0 && <MapLegend origins={legendItems} />}
          {!scrubbedPts.length && <aside className="map-empty" role="status">
            <h2>{modeCoordinates ? "No matching map locations" : hasCountryData ? "Country overview" : "No mapped places in this file"}</h2>
            <p>{modeCoordinates ? "No locations match these filters and timeline." : hasCountryData
              ? `Your records include countries, but no map coordinates for ${pinMode === "birth" ? "birthplaces" : "places of death"}. Shaded countries are still available.`
              : "Place names can be explored without coordinates. The family tree and research hints are available too."}</p>
            <div className="empty-actions">
              {chips.length > 0 && <button onClick={() => applyFilters(defaults)}>Clear filters</button>}
              {scrubMode !== "off" && <button onClick={() => changeScrubMode("off")}>Turn timeline off</button>}
              <button onClick={() => showPeople("People and recorded places", map.people)}>Browse recorded places</button>
              <button onClick={() => selectTab("fan")}>View family tree</button>
            </div>
          </aside>}
        </div>
      </div>}
      {tab === "fan" && <div className="stage stage-fan">
        <p className="view-scope">Chart: the starting person’s pedigree. Matches are highlighted; the generation table covers the whole tree.</p>
        {fanErr ? <TabError message={fanErr} /> : !fan ? <div className="loading" role="status">Loading family tree…</div>
          : fan.root ? <FanChart recs={fan.recs} root={fan.root} focus={fanFocus} filter={filter} genComposition={genComposition}
              onPerson={openPerson} onFocusChange={rememberFocus} /> : <div className="empty-state">No family relationships in this file.</div>}
      </div>}
      {tab === "migration" && <div className="stage stage-migration"><div className="insights">
        <h2>Migration paths <span className="scope-label">Matching your filters</span></h2>
        <p className="sub">Recorded origins to the first New-World settlement on each family line. Select a route to explore its people.</p>
        <p>{fimm.length.toLocaleString()} of {map.immigrants.length.toLocaleString()} immigrant ancestors match.</p>
        <Sankey data={sankey!} onPick={migrationList} />
        {!fimm.length && <p className="sub">No migration paths match. Try clearing filters, or explore the family tree for records that do not fit this migration model.</p>}
      </div></div>}
      {tab === "insights" && <div className="stage stage-insights"><StatsPanel insights={insights!} collapse={collapse!} dna={dna!}
        deadends={deadends} deadendsError={deadendsErr} duplicates={dups} people={fpeople} immigrants={fimm}
        onViewTree={viewInTree} onPerson={openPerson} onShowPeople={showPeople} /></div>}
    </main>
    {filtersOpen && <div className="modal-backdrop filter-backdrop" onClick={() => setFiltersOpen(false)}>
      <section ref={filterRef} id="explorer-filters" className="modal filter-panel" role="dialog" aria-modal="true" aria-labelledby="filter-title"
        tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" aria-label="Close filters" onClick={() => setFiltersOpen(false)}>×</button>
        <h2 id="filter-title" className="modal-title">Filter people</h2>
        <p className="sub">Narrow matching people, map pins, migration paths, and research lists. Whole-tree summaries stay unchanged.</p>
        <Filters filter={filter} setFilter={applyFilters} countries={countries} states={states} ranges={map.ranges} onReset={() => applyFilters(defaults)} />
        <button className="btn-primary filter-done" onClick={() => setFiltersOpen(false)}>Show {fpop.length.toLocaleString()} matching ancestors</button>
      </section>
    </div>}
    {countryIso && activeDetail && !activePerson && !activeList && <CountryModal iso={countryIso} name={activeName} detail={activeDetail}
      datum={map.country_data[countryIso]} colors={map.colors} onClose={closeCountry} onExplore={exploreCountry} />}
    {activeList && <PersonDrawer key={listId} title={activeList.title} people={activeList.people} searchable
      hidden={!!activePerson} onClose={closeList} onViewTree={viewInTree} onOpenPerson={openPerson} />}
    {activePerson && <PersonModal person={activePerson} recs={fan?.recs ?? null} root={fan?.root ?? null} colors={map.colors}
      onClose={closePerson} onBack={activeList ? closePerson : undefined} onViewTree={viewInTree} onOpenPerson={openPerson} />}
  </div>;
}

function TabError({ message }: { message: string }) {
  return <div className="insights"><div className="err" role="alert">Couldn’t load this view: {message}</div>
    <button onClick={() => window.location.reload()}>Retry</button></div>;
}
