const assert = require("node:assert/strict");
const { test } = require("node:test");
const { harness, nodes, find } = require("./test-helpers.cjs");

function page(api) {
  const navigated = [];
  const component = harness("pages/UploadPage.tsx", {
    "react-router-dom": { Link: "a", useNavigate: () => (url) => navigated.push(url) },
    "../api/client": { api },
    "../components/ImportGuide": () => null,
    "../lib/year": { formatYear: (year) => year < 0 ? `${-year} BC` : String(year) },
  });
  return { ...component, navigated };
}

const button = (tree, text) => find(tree, (node) => node.type === "button" && node.props.children === text);
const input = (tree) => find(tree, (node) => node.type === "input" && node.props.type === "file");
const radios = (tree) => nodes(tree).filter((node) => node.type === "input" && node.props.type === "radio");
const pick = (h, files) => input(h.render()).props.onChange({ target: { files } });
const drop = (tree, files) => find(tree, (node) => node.props?.onDrop).props.onDrop({
  preventDefault() {}, dataTransfer: { files },
});
const preview = {
  people: [{ id: "F0:@A@", name: "Avery Example", year: 1980, place: "Provo" },
    { id: "F1:@B@", name: "Blair Example", year: 1977, place: null }],
  suggested_root: "F0:@A@", candidate_count: 2,
};

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test("preview requires explicit person confirmation even for one suggested starting point", async () => {
  for (const candidate_count of [1, 2]) {
    const h = page({ preview: async () => ({ ...preview, candidate_count }) });
    pick(h, [{ name: "tree.ged" }]);
    await button(h.render(), "Find starting person").props.onClick();
    assert.equal(button(h.render(), "Import tree").props.disabled, true);
    assert.ok(radios(h.render()).every((radio) => radio.props.checked === false));
    radios(h.render())[1].props.onChange();
    assert.equal(button(h.render(), "Import tree").props.disabled, false);
    assert.equal(radios(h.render())[1].props.checked, true);
  }
});

test("reading and importing freeze file changes and importing errors allow retry", async () => {
  const reading = deferred(), importing = deferred();
  const files = [{ name: "original.ged" }];
  let uploaded;
  const h = page({ preview: () => reading.promise, upload: (chosen, root) => {
    uploaded = { chosen, root }; return importing.promise;
  } });
  pick(h, files);
  const readingPromise = button(h.render(), "Find starting person").props.onClick();
  let tree = h.render();
  assert.equal(input(tree).props.disabled, true);
  assert.equal(button(tree, "Choose GEDCOM files").props.disabled, true);
  drop(tree, [{ name: "ignored.ged" }]);
  pick(h, [{ name: "ignored.ged" }]);
  reading.resolve(preview);
  await readingPromise;
  radios(h.render())[1].props.onChange();
  const importingPromise = button(h.render(), "Import tree").props.onClick();
  tree = h.render();
  assert.equal(find(tree, (node) => node.type === "fieldset").props.disabled, true);
  assert.equal(input(tree).props.disabled, true);
  drop(tree, [{ name: "also-ignored.ged" }]);
  importing.reject(new Error("Connection lost"));
  await importingPromise;
  assert.deepEqual(uploaded, { chosen: files, root: "F1:@B@" });
  assert.match(find(h.render(), (node) => node.props?.role === "alert").props.children, /Connection lost.*Try importing again/);
  assert.equal(button(h.render(), "Import tree").props.disabled, false);
  assert.equal(input(h.render()).props.disabled, false);
  assert.equal(find(h.render(), (node) => node.type === "fieldset").props.disabled, false);
});

test("search reaches people outside the bounded list and changing files resets confirmation", async () => {
  const people = Array.from({ length: 101 }, (_, index) => ({
    id: `F0:@I${index}@`, name: `Person ${index}`, year: 1800 + index, place: null,
  }));
  const uploaded = [];
  const h = page({ preview: async () => ({ people, suggested_root: people[0].id, candidate_count: 101 }),
    upload: async (files, root) => { uploaded.push(root); return { id: "chosen" }; },
  });
  pick(h, [{ name: "large.ged" }]);
  await button(h.render(), "Find starting person").props.onClick();
  assert.equal(radios(h.render()).length, 40);
  find(h.render(), (node) => node.props?.id === "person-search").props.onChange({ target: { value: "Person 100" } });
  assert.equal(radios(h.render()).length, 1);
  assert.equal(radios(h.render())[0].props.value, "F0:@I100@");
  radios(h.render())[0].props.onChange();
  pick(h, [{ name: "replacement.ged" }]);
  assert.equal(button(h.render(), "Import tree"), undefined);
  assert.equal(radios(h.render()).length, 0);
  assert.ok(button(h.render(), "Find starting person"));
  assert.deepEqual(uploaded, []);
});

test("a confirmed starting person is sent on import and successful import opens the tree", async () => {
  let uploaded;
  const files = [{ name: "tree.ged" }];
  const h = page({ preview: async () => preview,
    upload: async (chosen, root) => { uploaded = { chosen, root }; return { id: "confirmed" }; },
  });
  pick(h, files);
  await button(h.render(), "Find starting person").props.onClick();
  radios(h.render())[1].props.onChange();
  await button(h.render(), "Import tree").props.onClick();
  assert.deepEqual(uploaded, { chosen: files, root: "F1:@B@" });
  assert.deepEqual(h.navigated, ["/tree/confirmed"]);
});

test("preview errors are actionable alerts and release the file picker for retry", async () => {
  const h = page({ preview: async () => { throw new Error("No people found"); } });
  pick(h, [{ name: "invalid.ged" }]);
  await button(h.render(), "Find starting person").props.onClick();
  assert.match(find(h.render(), (node) => node.props?.role === "alert").props.children,
    /No people found.*Choose a GEDCOM export and try again/);
  assert.equal(button(h.render(), "Find starting person").props.disabled, false);
  assert.equal(input(h.render()).props.disabled, false);
  pick(h, [{ name: "new.ged" }]);
  assert.equal(find(h.render(), (node) => node.props?.role === "alert"), undefined);
});
