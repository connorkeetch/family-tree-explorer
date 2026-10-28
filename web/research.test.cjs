const assert = require("node:assert/strict");
const { test } = require("node:test");
const { load, harness, nodes, text } = require("./test-helpers.cjs");

const { deriveSankey, sankeyMembers } = load("lib/insights.ts");
const immigrant = (origin, settlement, xref) => ({ origin, settlement, xref });

test("small migrations retain named routes and the same people in chart drills", () => {
  const people = [immigrant("Danish", "Utah", "a"), immigrant("English", "New York", "b"),
    immigrant("Irish", "Massachusetts", "c"), immigrant("German", "Pennsylvania", "d")];
  const chart = deriveSankey(people, {});
  assert.equal(chart.flows.length, 4);
  assert.equal(chart.total, 4);
  assert.ok(chart.flows.every((flow) => !flow.origin.startsWith("Other") && !flow.settlement.startsWith("Other")));
  for (const flow of chart.flows) assert.equal(sankeyMembers(people, flow).length, flow.count);
  assert.deepEqual(deriveSankey(people.slice(0, 1), {}).flows.map((f) => [f.origin, f.settlement]), [["Danish", "Utah"]]);
});

test("crowded migration rollups retain totals and resolve every node and route consistently", () => {
  const people = [];
  for (let i = 0; i < 12; i++) for (let j = 0; j <= i; j++) {
    people.push(immigrant(`Origin ${i}`, `State ${i}`, `${i}-${j}`));
  }
  people.push(immigrant("Origin 11", "(unknown)", "unknown"));
  const chart = deriveSankey(people, {});
  assert.equal(chart.total, people.length);
  assert.equal(chart.settled, people.length - 1);
  assert.ok(chart.flows.some((f) => f.origin === "Other origins" && f.settlement === "Other states"));
  assert.deepEqual(deriveSankey([...people].reverse(), {}), chart);
  for (const flow of chart.flows) assert.equal(sankeyMembers(people, flow).length, flow.count);
  for (const key of ["origin", "settlement"]) for (const label of new Set(chart.flows.map((f) => f[key]))) {
    assert.equal(sankeyMembers(people, { [key]: label }).length,
      chart.flows.filter((f) => f[key] === label).reduce((sum, f) => sum + f.count, 0));
  }
});

test("native migration controls reach the same chart selections", () => {
  const selections = [];
  const Sankey = load("viz/Sankey.tsx").default;
  const chart = Sankey({ data: deriveSankey([immigrant("Danish", "Utah", "a")], {}),
    onPick: (value) => selections.push(value) });
  const buttons = nodes(chart).filter((n) => n.type === "button");
  assert.equal(buttons.length, 3);
  for (const button of buttons) button.props.onClick();
  assert.deepEqual(selections, [{ origin: "Danish", settlement: "Utah" }, { origin: "Danish" }, { settlement: "Utah" }]);
});

test("research actions and names use the shared people list and person inspector", () => {
  const opened = [], inspected = [];
  const h = harness("viz/StatsPanel.tsx", {
    "../lib/year": { formatYear: String }, "../components/CombinedGuess": () => null,
  });
  const person = { name: "Unresolved Person", surname: "Person", xref: "p", fid: null,
    nat: "(untraced)", src: 0, dir: true, gen: 1 };
  const props = { insights: { completeness: [{ gen: 1, known: 2, expected: 2 }],
    surnames: [{ surname: "Person", count: 1, color: "gray" }],
    longevity: { n: 0, by_century: [], by_origin: [] }, immigration: { by_decade: [], total: 0, undated: 0 } },
    collapse: { n_collapse: 0, n_over_attached: 0, couples: [] },
    dna: { y_line: [{ ...person, color: "gray" }], mt_line: [] }, deadends: null,
    people: [person], immigrants: [], onViewTree: () => assert.fail("name should inspect the person"),
    onPerson: (xref) => inspected.push(xref), onShowPeople: (title, people) => opened.push({ title, people }) };
  const tree = h.render(props);
  const buttons = nodes(tree, true).filter((n) => n.type === "button");
  buttons.find((n) => text(n) === "Browse people and their places").props.onClick();
  buttons.find((n) => text(n) === "Check these records").props.onClick();
  buttons.find((n) => text(n).startsWith("Person1")).props.onClick();
  buttons.find((n) => text(n) === person.name).props.onClick();
  assert.equal(opened.length, 3);
  assert.ok(opened.every((list) => list.people.length === 1 && list.people[0].xref === "p"));
  assert.deepEqual(inspected, ["p"]);
  assert.equal(nodes(tree, true).filter((n) => n.type === "h2" && text(n).startsWith("By birth century")).length, 0);
  h.unmount();
});

test("missing-parent research finds grandparents even when every origin is resolved", () => {
  const opened = [];
  const h = harness("viz/StatsPanel.tsx", {
    "../lib/year": { formatYear: String }, "../components/CombinedGuess": () => null,
  });
  const grandparents = Array.from({ length: 4 }, (_, i) => ({ xref: `G${i}`, name: `Grandparent ${i}`,
    fid: null, surname: "Example", nat: "Danish", src: 1, gen: 2, missing_parents: 2 }));
  const props = { insights: { completeness: [], surnames: [], longevity: { n: 0, by_century: [], by_origin: [] },
    immigration: { by_decade: [], total: 0, undated: 0 } },
    collapse: { n_collapse: 0, n_over_attached: 0, couples: [] }, dna: { y_line: [], mt_line: [] },
    deadends: { untraced_pct: 0, wall_pct: 0, genuine_pct: 0, wall_generation: 2,
      top_genuine: [], likely_origin: [], by_reason: {} },
    people: [{ xref: "root", nat: "Danish", src: 1, missing_parents: 0 }, ...grandparents], immigrants: [],
    onViewTree() {}, onShowPeople: (title, people) => opened.push({ title, people }) };
  let tree = h.render(props);
  const missingCard = nodes(tree, true).find((n) => typeof n.type === "function" && n.props.title === "Where are parents missing?");
  const summary = nodes(missingCard, true).find((n) => n.type === "p");
  assert.deepEqual(nodes(summary).filter((n) => n.type === "b").map((n) => text(n).trim()), ["4", "8"]);
  assert.equal(nodes(tree, true).some((n) => n.type === "h2" && text(n) === "Records before the deepest imported generation"), false);
  const action = (result) => nodes(result, true).find((n) => n.type === "button" && text(n) === "Browse people with missing parents");
  assert.equal(action(tree).props.disabled, false);
  action(tree).props.onClick();
  assert.deepEqual(opened[0].people.map((p) => p.xref), ["G0", "G1", "G2", "G3"]);
  tree = h.render({ ...props, people: [{ ...grandparents[0], missing_parents: 1 }] });
  const filteredCard = nodes(tree, true).find((n) => typeof n.type === "function" && n.props.title === "Where are parents missing?");
  const filteredSummary = nodes(filteredCard, true).find((n) => n.type === "p");
  assert.deepEqual(nodes(filteredSummary).filter((n) => n.type === "b").map((n) => text(n).trim()), ["1", "1"]);
  action(tree).props.onClick();
  assert.deepEqual(opened[1].people.map((p) => p.xref), ["G0"], "the lead list follows the filtered people, independently of the origin-gap payload");
  assert.equal(action(h.render({ ...props, people: [{ missing_parents: 0, src: 1 }] })).props.disabled, true);
  h.unmount();
});

test("fan keyboard selector and history persist focus through parent URL echoes", () => {
  const h = harness("viz/FanChart.tsx", {
    "../lib/filter": load("lib/filter.ts"), "../lib/fanLayout": load("lib/fanLayout.ts"),
    "../components/CombinedGuess": () => null, "./GenerationBreakdown": () => null,
  });
  const focus = [];
  const rec = (name, gen, fa = null) => ({ n: name, g: name, gen, fa, mo: null, nat: "English" });
  const props = { root: "root", recs: { root: rec("Root", 0, "F"), F: rec("Father", 1, "G"), G: rec("Grandfather", 2) },
    filter: { branch: "all", country: "all", state: "all", sex: "all", dna: "all", yrMin: 0, yrMax: 2100, genMin: 0, genMax: 8 },
    onFocusChange: (xref) => focus.push(xref) };
  const render = () => h.render(props);
  let tree = render();
  [...nodes(tree)].find((n) => n.type === "select").props.onChange({ target: { value: "F" } });
  tree = render();
  assert.deepEqual(focus, []);
  [...nodes(tree)].find((n) => n.type === "button" && text(n) === "Show this branch").props.onClick();
  props.focus = { xref: "F" };
  tree = render();
  assert.equal([...nodes(tree)].find((n) => n.type === "select").props.value, "F");
  const back = [...nodes(tree)].find((n) => n.type === "button" && text(n).includes("Back"));
  assert.equal(back.props.disabled, false);
  back.props.onClick();
  props.focus = { xref: "root" };
  render();
  tree = render();
  assert.equal([...nodes(tree)].find((n) => n.type === "select").props.value, "root");
  assert.deepEqual(focus, ["F", "root"]);
  h.unmount();
});
