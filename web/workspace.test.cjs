const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const { test } = require("node:test");
const ts = require("typescript");

function load(file, mocks = {}) {
  const filename = path.join(__dirname, "src", file);
  const js = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  const localRequire = createRequire(filename);
  const module = { exports: {} };
  new Function("require", "module", "exports", js)(
    (name) => name in mocks ? mocks[name] : localRequire(name), module, module.exports,
  );
  return module.exports;
}

const { AMERICAN, FILTER_KEYS, defaultFilter, readFilter, writeFilter, matchDecade } = load("lib/filter.ts");
const ranges = { yr_lo: -2500, yr_hi: 2026, gen_lo: 0, gen_hi: 20 };

test("URL filters round-trip every selection while retaining view and inspector history", () => {
  const original = new URLSearchParams("view=fan&person=I42&focus=I7&list=missing&q=Smith");
  const selected = { branch: "P", country: AMERICAN, state: "Utah", sex: "F", dna: "mt",
    yrMin: -200, yrMax: 1900, genMin: 2, genMax: 9 };
  const written = writeFilter(original, selected, ranges);
  assert.deepEqual(readFilter(written, ranges), selected);
  for (const key of ["view", "person", "focus", "list", "q"]) assert.equal(written.get(key), original.get(key));
  assert.equal(original.has("origin"), false, "writing filters does not mutate the existing history entry");
  const reset = writeFilter(written, defaultFilter(ranges), ranges);
  assert.ok(FILTER_KEYS.every((key) => !reset.has(key)));
  assert.equal(reset.toString(), original.toString());
});

test("URL filters reject malformed values, clamp ranges, and normalize crossed endpoints", () => {
  const malformed = readFilter(new URLSearchParams(
    "branch=other&sex=X&line=DNA&origin=French&state=Utah&yearMin=NaN&yearMax=Infinity&genMin=&genMax=bad"), ranges);
  assert.deepEqual(malformed, { ...defaultFilter(ranges), country: "French" });
  const clamped = readFilter(new URLSearchParams("yearMin=-9999&yearMax=9999&genMin=-10&genMax=999"), ranges);
  assert.deepEqual(clamped, defaultFilter(ranges));
  const crossed = readFilter(new URLSearchParams("yearMin=1900.6&yearMax=1500&genMin=15.4&genMax=2"), ranges);
  assert.equal(crossed.yrMin, 1901);
  assert.equal(crossed.yrMax, 1901);
  assert.equal(crossed.genMin, 15);
  assert.equal(crossed.genMax, 15);
  const zero = readFilter(new URLSearchParams("yearMin=0&yearMax=0&genMin=0&genMax=0"), ranges);
  assert.equal(zero.yrMin, 0);
  assert.equal(zero.yrMax, 0);
  assert.equal(zero.genMax, 0);
  assert.equal(readFilter(new URLSearchParams("yearMin=%20%20&yearMax=%20%20"), ranges).yrMin, ranges.yr_lo);
});

test("recorded lifetimes require valid birth and death years and overlap the selected decade", () => {
  const matches = (year, dyear, decade = 1800) => matchDecade("alive", decade, { year, dyear });
  assert.equal(matches(1700, null), false);
  assert.equal(matches(1700, undefined), false);
  assert.equal(matches(null, 1850), false);
  assert.equal(matches(1805, 1804), false);
  assert.equal(matches(1700, 1799), false);
  assert.equal(matches(1810, 1880), false);
  assert.equal(matches(1700, 1800), true);
  assert.equal(matches(1809, 1810), true);
  assert.equal(matches(-30, -11, -20), true);
  assert.equal(matches(-30, -21, -20), false);
  assert.equal(matches(0, 0, 0), true);
  assert.equal(matchDecade("off", 1800, { year: null, dyear: null }), true);
});

test("born-through-decade filtering preserves BC and year-zero records without inferring death", () => {
  for (const year of [-100, -1, 0, 9]) assert.equal(matchDecade("born", 0, { year, dyear: null }), true);
  assert.equal(matchDecade("born", 0, { year: 10, dyear: null }), false);
  assert.equal(matchDecade("born", -20, { year: -11, dyear: null }), true);
  assert.equal(matchDecade("born", -20, { year: -10, dyear: null }), false);
  assert.equal(matchDecade("born", 0, { year: null, dyear: 1 }), false);
});

function find(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) {
    const found = find(child, predicate);
    if (found) return found;
  }
  return null;
}

// Execute component effects with the same dependency/cleanup behavior across renders.
function renderer(Component, react) {
  const slots = [];
  const changed = (old, next) => !old || old.length !== next.length || old.some((value, i) => !Object.is(value, next[i]));
  return {
    render(props) {
      let cursor = 0;
      const effects = [];
      react.useState = (initial) => {
        const index = cursor++;
        slots[index] ??= { value: typeof initial === "function" ? initial() : initial };
        return [slots[index].value, (value) => {
          slots[index].value = typeof value === "function" ? value(slots[index].value) : value;
        }];
      };
      react.useRef = (initial) => slots[cursor++] ??= { current: initial };
      react.useMemo = (factory, deps) => {
        const index = cursor++;
        if (changed(slots[index]?.deps, deps)) slots[index] = { value: factory(), deps };
        return slots[index].value;
      };
      react.useEffect = (effect, deps) => {
        const index = cursor++;
        if (changed(slots[index]?.deps, deps)) effects.push({ index, effect, deps });
      };
      const tree = Component(props);
      for (const { index } of effects) slots[index]?.cleanup?.();
      for (const { index, effect, deps } of effects) slots[index] = { deps, cleanup: effect() };
      return tree;
    },
    unmount() { for (const slot of slots) slot?.cleanup?.(); },
  };
}

function mapFixture(initialCamera) {
  const react = { memo: (component) => component };
  const fits = [], views = [], saved = [], events = new Map();
  let center, zoom, created = 0, removed = 0;
  const map = {
    setView(nextCenter, nextZoom) { center = nextCenter; zoom = nextZoom; views.push({ center, zoom }); return this; },
    fitBounds(bounds, options) { fits.push({ bounds, options }); },
    getCenter: () => ({ lat: center[0], lng: center[1] }), getZoom: () => zoom,
    on(names, handler) { for (const name of names.split(" ")) events.set(name, handler); },
    off(names) { for (const name of names.split(" ")) events.delete(name); },
    remove() { removed++; },
  };
  const OriginsMap = load("viz/OriginsMap.tsx", { react,
    leaflet: { map: () => { created++; return map; }, tileLayer: () => ({ addTo() {} }), latLngBounds: (points) => points },
    supercluster: class {}, "../lib/year": { formatYear: String },
  }).default;
  const component = renderer(OriginsMap, react);
  let props = { points: [], arcs: [], showArcs: false, coordMode: "birth", countryData: {}, countryDetails: {},
    initialCamera, onCameraChange: (camera) => saved.push(camera) };
  component.render(props);
  let tree = component.render(props);
  const fit = renderer(find(tree, (node) => node.type?.name === "FitBounds").type, react);
  return {
    fits, views, saved, events, map,
    render(next = {}) {
      props = { ...props, ...next };
      tree = component.render(props);
      fit.render(find(tree, (node) => node.type?.name === "FitBounds").props);
      return tree;
    },
    unmount() { fit.unmount(); component.unmount(); assert.equal(removed, 1); assert.equal(events.size, 0); },
    created: () => created,
  };
}

test("map waits for its first points, fits once, and preserves the camera through selection and timeline updates", () => {
  const fixture = mapFixture();
  const first = { xref: "a", lat: 40, lon: -111, dlat: 41, dlon: -110 };
  const second = { xref: "b", lat: 55, lon: 12, dlat: 56, dlon: 13 };
  fixture.render();
  assert.equal(fixture.fits.length, 0);
  fixture.render({ points: [first, second] });
  assert.equal(fixture.fits.length, 1);
  assert.deepEqual(fixture.fits[0].bounds, [[40, -111], [55, 12]]);
  assert.deepEqual(fixture.fits[0].options, { padding: [30, 30], maxZoom: 8 });
  fixture.render({ points: [second] });
  fixture.render({ points: [], coordMode: "death" });
  const tree = fixture.render({ points: [second], coordMode: "death" });
  assert.equal(fixture.fits.length, 1, "filter, time, and pin-mode changes keep the user's camera");
  find(tree, (node) => node.type === "button" && node.props.className === "map-fit").props.onClick();
  assert.equal(fixture.fits.length, 2);
  assert.deepEqual(fixture.fits[1].bounds, [[56, 13]], "explicit fitting uses the current selection and coordinate mode");
  const empty = fixture.render({ points: [] });
  assert.equal(find(empty, (node) => node.type === "button" && node.props.className === "map-fit").props.disabled, true);
  assert.equal(fixture.created(), 1);
  assert.equal(fixture.views.length, 1);
  fixture.unmount();
});

test("map restores a saved camera without auto-fitting and remembers later navigation", () => {
  const initialCamera = { center: [48.8, 2.3], zoom: 7 };
  const fixture = mapFixture(initialCamera);
  fixture.render({ points: [{ lat: 40, lon: -111 }] });
  assert.deepEqual(fixture.views, [initialCamera]);
  assert.equal(fixture.fits.length, 0);
  fixture.map.setView([51.5, -0.1], 9);
  fixture.events.get("moveend")();
  assert.deepEqual(fixture.saved.at(-1), { center: [51.5, -0.1], zoom: 9 });
  const tree = fixture.render({ points: [{ lat: 55, lon: 12 }] });
  assert.equal(fixture.fits.length, 0);
  find(tree, (node) => node.type === "button" && node.props.className === "map-fit").props.onClick();
  assert.deepEqual(fixture.fits[0].bounds, [[55, 12]]);
  fixture.unmount();
  assert.deepEqual(fixture.saved.at(-1), { center: [51.5, -0.1], zoom: 9 });
});
