const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const { execFileSync } = require("node:child_process");
const { load, harness, nodes, find, flush, globalValue } = require("./test-helpers.cjs");

test("the browser build includes original and dependency license notices", () => {
  execFileSync(process.execPath, [path.join(__dirname, "scripts", "licenses.cjs")]);
  const notices = fs.readFileSync(path.join(__dirname, "public", "third-party-licenses.txt"), "utf8");
  assert.match(notices, /Copyright \(c\) 2026 connorkeetch/);
  assert.match(notices, /leaflet .*BSD-2-Clause/);
  assert.match(notices, /Volodymyr Agafonkin/);
  assert.match(notices, /react-router .*MIT/);
  assert.doesNotMatch(notices, /Hippocratic/);
});

const { deriveGenComposition } = load("lib/insights.ts");
const { lineageOf } = load("lib/lineage.ts");
const { layoutFan, FAN_POSITION_LIMIT } = load("lib/fanLayout.ts");
const rec = (gen, fa = null, mo = null) => ({ gen, fa, mo, nat: "English" });

test("a repeated grandparent fills both documented positions", () => {
  const recs = { root: rec(0, "F", "M"), F: rec(1, "G1", "G2"), M: rec(1, "G1", "G3"),
    G1: rec(2), G2: rec(2), G3: rec(2) };
  const row = deriveGenComposition(recs, "root", {})[2];
  assert.equal(row.known, 4);
  assert.deepEqual(row.segments.map(({ name, count, pct }) => ({ name, count, pct })),
    [{ name: "English", count: 4, pct: 100 }]);
  recs.M.mo = null;
  const missing = deriveGenComposition(recs, "root", {})[2];
  assert.equal(missing.known, 3);
  assert.equal(missing.segments.find((s) => s.name === "Unknown").pct, 25);
});

test("generation composition combines deep repeated positions and cuts cycles", () => {
  const recs = { root: rec(0, "a1", "b1") };
  for (let g = 1; g <= 24; g++) {
    for (const p of ["a", "b"]) recs[p + g] = rec(g, g < 24 ? "a" + (g + 1) : null,
      g < 24 ? "b" + (g + 1) : null);
  }
  const rows = deriveGenComposition(recs, "root", {});
  assert.equal(rows[24].segments[0].count, 2 ** 24);
  assert.equal(rows[24].segments[0].pct, 100);
  const cycle = deriveGenComposition({ root: rec(0, "A"), A: rec(1, "root"), unrelated: rec(3) }, "root", {});
  assert.equal(cycle.length, 2);
  assert.equal(cycle[1].segments.find((s) => s.name === "Unknown").pct, 50);
  assert.deepEqual(deriveGenComposition({}, null, {}), []);
});

test("an ancestor appearing at different depths is counted in each generation", () => {
  const rows = deriveGenComposition({ root: rec(0, "F", "M"), F: rec(1, "M"),
    M: rec(1, "G"), G: rec(2) }, "root", {});
  assert.equal(rows.length, 4);
  assert.equal(rows[2].known, 2);
  assert.equal(rows[3].known, 1);
  assert.equal(rows[3].segments.find((s) => s.name === "English").pct, 12.5);
});

test("lineage follows the selected root despite alternate claims and cycles", () => {
  const recs = { root: rec(0, "B"), A: rec(1, "G"), B: rec(1, "G"), G: rec(2, "root") };
  assert.deepEqual(lineageOf("G", recs, "root"), [
    { xref: "root", rel: null }, { xref: "B", rel: "father" }, { xref: "G", rel: "father" },
  ]);
  assert.equal(lineageOf("A", recs, "root"), null);
  assert.equal(lineageOf("missing", recs, "root"), null);
});

test("fan layout caps complete rings even for a cyclic repeated pedigree", () => {
  const recs = { root: rec(0, "A", "B"), A: rec(1, "A", "B"), B: rec(1, "A", "B") };
  const layout = layoutFan(recs, "root", 100);
  assert.equal(layout.limited, true);
  assert.ok(layout.filled.length + layout.gaps.length <= FAN_POSITION_LIMIT);
  assert.equal(layout.filled.length, 2 ** (layout.rings + 1) - 1);
  assert.ok(layout.filled.every((p) => p.g <= layout.rings));
});

test("fan layout keeps deep sparse lines available", () => {
  const recs = {};
  for (let g = 0; g <= 60; g++) recs[g] = rec(g, g < 60 ? String(g + 1) : null);
  const layout = layoutFan(recs, "0", 60);
  assert.equal(layout.limited, false);
  assert.equal(layout.rings, 60);
  assert.equal(layout.filled.length, 61);
});

test("upload has a native keyboard-accessible file chooser", () => {
  let clicks = 0;
  const h = harness("pages/UploadPage.tsx", {
    "react-router-dom": { useNavigate: () => () => {}, Link: "a" },
    "../api/client": { api: {} }, "../components/ImportGuide": () => null,
    "../lib/year": { formatYear: String },
  }, { beforeEffects(tree) {
    find(tree, (n) => n.type === "input" && n.props.type === "file").props.ref.current = { click: () => clicks++ };
  } });
  const button = find(h.render(), (n) => n.type === "button" && n.props.children === "Choose GEDCOM files");
  assert.ok(button);
  assert.equal(button.props.disabled, false);
  button.props.onClick();
  assert.equal(clicks, 1);
  h.unmount();
});

test("failed tree deletion displays an error and restores cancellation and retry", async () => {
  const tree = { id: "test", meta: { root: "Test", n_direct: 1, max_gen: 1 } };
  const Dialog = () => null;
  const dialogView = harness("components/ConfirmDialog.tsx", { "../lib/useFocusTrap": { useFocusTrap() {} } });
  let calls = 0;
  const h = harness("pages/LandingPage.tsx", {
    "react-router-dom": { useNavigate: () => () => {}, Link: "a" },
    "../auth/AuthContext": { useAuth: () => ({ user: { email: "test@example.com" } }) },
    "../components/ConfirmDialog": Dialog, "../components/Skeleton": () => null,
    "../api/client": { api: { listTrees: async () => [tree],
      deleteTree: async () => { calls++; throw new Error("Connection lost"); } } },
  });
  h.render();
  await flush();
  find(h.render(), (n) => n.type === "button" && n.props.children === "Delete tree").props.onClick();
  await find(h.render(), (n) => n.type === Dialog).props.onConfirm();
  let dialog = find(h.render(), (n) => n.type === Dialog);
  assert.equal(dialog.props.error, "Connection lost");
  assert.equal(find(dialogView.render(dialog.props), (n) => n.props?.role === "alert").props.children, "Connection lost");
  assert.equal(dialog.props.confirmLabel, "Delete tree");
  await dialog.props.onConfirm();
  assert.equal(calls, 2);
  dialog = find(h.render(), (n) => n.type === Dialog);
  dialog.props.onCancel();
  assert.equal(find(h.render(), (n) => n.type === Dialog), undefined);
  h.unmount();
  dialogView.unmount();
});

test("example action imports the bundled fictional GEDCOM through the normal upload", async (t) => {
  const example = fs.readFileSync(path.join(__dirname, "public/example.ged"), "utf8");
  assert.match(example, /fictional demonstration family/);
  assert.doesNotMatch(example, /_FSFTID|familysearch\.org/i);
  let fetched, uploaded;
  const navigated = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    fetched = url;
    return new Response(example);
  });
  const h = harness("pages/LandingPage.tsx", {
    "react-router-dom": { useNavigate: () => (url) => navigated.push(url), Link: "a" },
    "../auth/AuthContext": { useAuth: () => ({ user: { email: "test@example.com" } }) },
    "../components/ConfirmDialog": () => null, "../components/Skeleton": () => null,
    "../api/client": { api: { listTrees: async () => [],
      upload: async (files) => { uploaded = files; return { id: "example" }; } } },
  });
  await find(h.render(), (n) => n.type === "button" && n.props.children === "Try an example tree").props.onClick();
  assert.equal(fetched, "/example.ged");
  assert.equal(uploaded.length, 1);
  assert.equal(uploaded[0].name, "example.ged");
  assert.equal(await uploaded[0].text(), example);
  assert.deepEqual(navigated, ["/tree/example"]);
  h.unmount();
});

test("failed example loading and upload show an error and allow retry", async (t) => {
  let fetches = 0, uploads = 0;
  const navigated = [];
  t.mock.method(globalThis, "fetch", async () => {
    fetches++;
    return fetches === 1 ? new Response("missing", { status: 404 }) : new Response("example GEDCOM");
  });
  const h = harness("pages/LandingPage.tsx", {
    "react-router-dom": { useNavigate: () => (url) => navigated.push(url), Link: "a" },
    "../auth/AuthContext": { useAuth: () => ({ user: { email: "test@example.com" } }) },
    "../components/ConfirmDialog": () => null, "../components/Skeleton": () => null,
    "../api/client": { api: { listTrees: async () => [], upload: async () => {
      uploads++;
      if (uploads === 1) throw new Error("Upload failed. Please try again.");
      return { id: "retried" };
    } } },
  });
  const action = () => find(h.render(), (n) => n.type === "button" && n.props.children === "Try an example tree");
  await action().props.onClick();
  assert.match(find(h.render(), (n) => n.props?.role === "alert").props.children, /Could not load/);
  assert.equal(action().props.disabled, false);
  assert.equal(uploads, 0);
  await action().props.onClick();
  assert.equal(find(h.render(), (n) => n.props?.role === "alert").props.children, "Upload failed. Please try again.");
  assert.equal(action().props.disabled, false);
  await action().props.onClick();
  assert.equal(find(h.render(), (n) => n.props?.role === "alert"), undefined);
  assert.deepEqual(navigated, ["/tree/retried"]);
  h.unmount();
});

test("bundled country boundaries retain canonical ISO codes and public-domain provenance", () => {
  const world = JSON.parse(fs.readFileSync(path.join(__dirname, "public/world-countries.geojson"), "utf8"));
  assert.equal(world.type, "FeatureCollection");
  assert.match(world.source, /natural-earth-vector\/[0-9a-f]{40}\/geojson\//);
  assert.match(world.license, /Natural Earth public domain/);
  assert.equal(world.features.length, 177);
  const countries = new Map(world.features.map((f) => [f.id, f]));
  assert.equal(countries.size, world.features.length);
  for (const [iso, name] of [["FRA", "France"], ["NOR", "Norway"], ["GBR", "United Kingdom"],
    ["DNK", "Denmark"], ["IRL", "Ireland"], ["USA", "United States of America"]]) {
    assert.equal(countries.get(iso).properties.name, name);
  }
  for (const feature of world.features) {
    assert.match(feature.id, /^[A-Z]{3}$/);
    assert.ok(["Polygon", "MultiPolygon"].includes(feature.geometry.type));
  }
});

test("the direct Leaflet map releases its instance on unmount", () => {
  let created = 0, removed = 0, tiles = 0;
  const element = {};
  const leaflet = {
    map(container, options) {
      assert.equal(container, element);
      assert.equal(options.worldCopyJump, true);
      created++;
      return { setView() { return this; }, remove() { removed++; } };
    },
    tileLayer(url, options) {
      assert.equal(url, "https://tile.openstreetmap.org/{z}/{x}/{y}.png");
      assert.match(options.attribution, /Natural Earth/);
      return { addTo() { tiles++; } };
    },
  };
  const h = harness("viz/OriginsMap.tsx", {
    leaflet, supercluster: class {}, "../lib/year": { formatYear: String },
  }, { beforeEffects(tree) { find(tree, (n) => n.props?.ref).props.ref.current = element; } });
  h.render({ points: [], arcs: [], showArcs: false });
  assert.equal(created, 1);
  assert.equal(tiles, 1);
  h.unmount();
  assert.equal(removed, 1);
});

test("popup auto-pan retains visible markers and actions while filtering still removes them", async (t) => {
  const { default: Supercluster } = await import("supercluster");
  const node = (tag) => ({ tag, children: [], style: {}, append(...children) { this.children.push(...children); } });
  globalValue(t, "document", { createTextNode: (text) => ({ textContent: text }), createElement: node });
  const groups = [], created = [], events = new Map(), actions = [];
  let bounds = [-120, 20, 60, 70];
  const map = {
    setView() { return this; }, remove() {},
    getBounds: () => ({ getWest: () => bounds[0], getSouth: () => bounds[1],
      getEast: () => bounds[2], getNorth: () => bounds[3] }),
    getZoom: () => 17,
    on(names, handler) { for (const name of names.split(" ")) events.set(name, handler); },
    off(names) { for (const name of names.split(" ")) events.delete(name); },
  };
  const leaflet = {
    map: () => map, tileLayer: () => ({ addTo() {} }),
    divIcon: () => ({}),
    DomUtil: { create(tag, className, parent) { const el = node(tag); parent?.append(el); return el; } },
    layerGroup() {
      const group = {
        markers: new Set(), addTo() { return this; },
        removeLayer(marker) { this.markers.delete(marker); marker.popupOpen = false; marker.removed = true; },
        remove() { for (const marker of this.markers) this.removeLayer(marker); },
      };
      groups.push(group);
      return group;
    },
    marker(coords) {
      const marker = {
        coords, bindTooltip() { return this; }, bindPopup(content) { this.popup = content; return this; },
        addTo(group) { group.markers.add(this); return this; },
        openPopup() { this.popupOpen = true; this.content = this.popup(); },
      };
      created.push(marker);
      return marker;
    },
  };
  // Obtain the private marker component through the map's rendered children.
  const parent = harness("viz/OriginsMap.tsx", {
    leaflet, supercluster: Supercluster, "../lib/year": { formatYear: String },
  });
  const parentProps = { points: [], arcs: [], showArcs: false };
  parent.render(parentProps);
  const ClusteredMarkers = find(parent.render(parentProps), (n) => n.type?.name === "ClusteredMarkers").type;
  const markers = harness(ClusteredMarkers, { react: parent.react });
  const points = [{ xref: "one", name: "One", lat: 35, lon: -100, color: "#111", nat: "American" },
    { xref: "two", name: "Two", lat: 50, lon: 30, color: "#222", nat: "Ukrainian" }];
  let props = { map, points, coordMode: "birth", onPerson: (xref) => actions.push(["details", xref]),
    onViewTree: (xref) => actions.push(["fan", xref]) };
  const render = () => markers.render(props);
  render();
  render(); // The viewport effect has populated view state.
  assert.equal(created.length, 2);
  const source = created.find((marker) => marker.coords[1] === -100);
  source.openPopup();
  bounds = [-115, 20, -80, 70]; // Popup auto-pan also moves another marker off screen.
  events.get("moveend")();
  render();
  assert.equal(created.length, 2, "visible markers are reused, not replaced");
  assert.ok(groups[0].markers.has(source));
  assert.equal(groups[0].markers.size, 1);
  assert.equal(source.popupOpen, true);
  for (const button of nodes(source.content).filter((el) => el.tag === "button")) button.onclick();
  assert.deepEqual(actions, [["details", "one"], ["fan", "one"]]);
  props = { ...props, points: [points[1]] };
  render();
  assert.equal(source.removed, true, "filter changes discard markers from the old index");
  assert.equal(source.popupOpen, false);
  markers.unmount();
  parent.unmount();
  assert.equal(events.size, 0);
  assert.ok(groups.every((group) => group.markers.size === 0));
});
