const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const { load } = require("./test-helpers.cjs");

const { deriveSankey, sankeyMembers } = load("lib/insights.ts");
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, "../tests/fixtures/migration.json"), "utf8"));

for (const scenario of fixture.cases) {
  test(`shared API/browser migration contract: ${scenario.name}`, () => {
    const people = scenario.routes.flatMap(([origin, settlement, count], route) =>
      Array.from({ length: count }, (_, person) => ({ origin, settlement, xref: `${route}-${person}` })));
    const colors = scenario.colors || {};
    const chart = deriveSankey(people, colors);
    assert.deepEqual({ routes: chart.flows.map((f) => [f.origin, f.settlement, f.count]),
      total: chart.total, settled: chart.settled }, scenario.expected);
    assert.deepEqual(deriveSankey([...people].reverse(), colors), chart);
    for (const flow of chart.flows) {
      assert.equal(flow.color, colors[flow.origin] || "#6b7280");
      assert.equal(sankeyMembers(people, flow).length, flow.count);
    }
    for (const key of ["origin", "settlement"]) {
      for (const label of new Set(chart.flows.map((f) => f[key]))) {
        assert.equal(sankeyMembers(people, { [key]: label }).length,
          chart.flows.filter((f) => f[key] === label).reduce((sum, f) => sum + f.count, 0));
      }
    }
  });
}
