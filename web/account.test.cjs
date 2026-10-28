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

function harness(file, mocks, exported = "default") {
  const slots = [];
  let cursor = 0, pending = [];
  const changed = (a, b) => !a || a.length !== b.length || a.some((value, i) => !Object.is(value, b[i]));
  const react = {
    createContext: () => ({ Provider: "provider" }),
    useState(initial) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = { value: typeof initial === "function" ? initial() : initial };
      return [slots[i].value, (value) => { slots[i].value = typeof value === "function" ? value(slots[i].value) : value; }];
    },
    useRef(initial) { const i = cursor++; return slots[i] ??= { current: initial }; },
    useMemo(factory, deps) {
      const i = cursor++;
      if (changed(slots[i]?.deps, deps)) slots[i] = { deps, value: factory() };
      return slots[i].value;
    },
    useEffect(effect, deps) {
      const i = cursor++;
      if (changed(slots[i]?.deps, deps)) pending.push({ i, effect, deps });
    },
  };
  const Component = load(file, { react, ...mocks })[exported];
  return {
    render(...args) {
      cursor = 0;
      pending = [];
      const output = Component(...args);
      for (const { i } of pending) slots[i]?.cleanup?.();
      for (const { i, effect, deps } of pending) slots[i] = { deps, cleanup: effect() };
      return output;
    },
    unmount() { for (const slot of slots) slot?.cleanup?.(); },
  };
}

function all(node, predicate) {
  if (!node || typeof node !== "object") return [];
  return [...(predicate(node) ? [node] : []),
    ...[node.props?.children].flat(Infinity).flatMap((child) => all(child, predicate))];
}
const find = (node, predicate) => all(node, predicate)[0];
const flush = () => new Promise(setImmediate);
function globalValue(t, name, value) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
  t.after(() => previous ? Object.defineProperty(globalThis, name, previous) : delete globalThis[name]);
}

test("protected 401 expires cached authentication; credential and initial-session failures stay local", async (t) => {
  const events = new EventTarget();
  globalValue(t, "window", events);
  let expired = 0;
  events.addEventListener("kinwhere:unauthorized", () => expired++);
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ detail: "invalid email or password" }), { status: 401 }));
  const { api } = load("api/client.ts");
  for (const request of [() => api.me(), () => api.login("a@example.com", "wrong"),
    () => api.register("a@example.com", "password")]) {
    await assert.rejects(request, (error) => error.status === 401 && error.message === "invalid email or password");
  }
  assert.equal(expired, 0);
  await assert.rejects(() => api.listTrees(), (error) => error.status === 401 && /sign-in has expired/.test(error.message));
  assert.equal(expired, 1);

  let calls = 0;
  const h = harness("auth/AuthContext.tsx", { "../api/client": { api: {
    me: async () => { calls++; return { id: 1, email: "a@example.com" }; },
  } } }, "AuthProvider");
  h.render({ children: null });
  await flush();
  assert.equal(h.render({ children: null }).props.value.user.id, 1);
  events.dispatchEvent(new Event("kinwhere:unauthorized"));
  const value = h.render({ children: null }).props.value;
  assert.equal(value.user, null);
  assert.equal(value.loading, false);
  assert.equal(calls, 1, "clearing a session must not re-run the initial account request");
  h.unmount();
});

test("request errors explain validation and connection failures without submitted inputs", async (t) => {
  const { api } = load("api/client.ts");
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ detail: [
    { loc: ["body", "password"], msg: "Use at least 8 characters", input: "private-password", ctx: { secret: "private-password" } },
    { loc: ["body", "email"], msg: "Use an email address", input: "private@example.com" },
  ] }), { status: 422 }));
  await assert.rejects(() => api.register("private@example.com", "private-password"), (error) => {
    assert.match(error.message, /password: Use at least 8 characters/);
    assert.match(error.message, /email: Use an email address/);
    assert.doesNotMatch(error.message, /private|object Object/);
    return error.status === 422;
  });
  globalThis.fetch = async () => { throw new Error("network internals: private-password"); };
  await assert.rejects(() => api.listTrees(), (error) => /Could not connect/.test(error.message) && !/private-password/.test(error.message));
  globalThis.fetch = async () => new Response("private-password: unexpected HTML");
  await assert.rejects(() => api.listTrees(), (error) => /Could not read the response/.test(error.message) && !/private-password/.test(error.message));
});

test("login retains credential errors, then returns to the intended local tree", async () => {
  const navigated = [];
  const auth = { user: null, loading: false, login: async () => { throw new Error("Invalid email or password"); } };
  const h = harness("pages/LoginPage.tsx", {
    "react-router-dom": { useNavigate: () => (...args) => navigated.push(args),
      useLocation: () => ({ state: { from: "/tree/saved?view=fan" } }), Navigate: "redirect" },
    "../auth/AuthContext": { useAuth: () => auth },
  });
  let view = h.render();
  find(view, (n) => n.props?.id === "account-email").props.onChange({ target: { value: "me@example.com" } });
  find(view, (n) => n.props?.id === "account-password").props.onChange({ target: { value: "wrong" } });
  await find(h.render(), (n) => n.type === "form").props.onSubmit({ preventDefault() {} });
  view = h.render();
  assert.equal(find(view, (n) => n.props?.role === "alert").props.children, "Invalid email or password");
  assert.deepEqual(navigated, []);
  assert.equal(find(view, (n) => n.props?.type === "submit").props.disabled, false);
  auth.login = async (email, password) => { assert.equal(email, "me@example.com"); assert.equal(password, "wrong"); };
  await find(h.render(), (n) => n.type === "form").props.onSubmit({ preventDefault() {} });
  assert.deepEqual(navigated, [["/tree/saved?view=fan", { replace: true }]]);
  find(h.render(), (n) => n.type === "button" && n.props.children === "Create account").props.onClick();
  assert.equal(find(h.render(), (n) => n.props?.id === "account-password").props.minLength, 8);
});

test("login rejects external destinations and routes back to login", () => {
  for (const from of ["https://example.com", "//example.com", "/\\example.com", "/login", "/login?again=1", "/tree/\nother", {}, null]) {
    const h = harness("pages/LoginPage.tsx", {
      "react-router-dom": { useNavigate: () => () => {}, useLocation: () => ({ state: { from } }), Navigate: "redirect" },
      "../auth/AuthContext": { useAuth: () => ({ user: { id: 1 }, loading: false }) },
    });
    assert.equal(h.render().props.to, "/");
  }
});

test("a failed library request shows Retry instead of an empty library and recovers", async () => {
  let calls = 0;
  const tree = { id: "saved", created_at: "2026-10-20T12:34:56", meta: {
    root: "Example", n_direct: 12, max_gen: 4, source_files: ["example.ged"],
  } };
  const h = harness("pages/LandingPage.tsx", {
    "react-router-dom": { useNavigate: () => () => {}, Link: "link" },
    "../auth/AuthContext": { useAuth: () => ({ user: { email: "me@example.com" } }) },
    "../components/ConfirmDialog": () => null, "../components/Skeleton": () => null,
    "../api/client": { api: { listTrees: async () => { if (++calls === 1) throw new Error("Connection lost"); return [tree]; } } },
  });
  assert.ok(find(h.render(), (n) => n.props?.role === "status"));
  await flush();
  let view = h.render();
  assert.ok(find(view, (n) => n.props?.role === "alert"));
  assert.equal(find(view, (n) => n.props?.className === "card empty-state"), undefined);
  await find(view, (n) => n.type === "button" && n.props.children === "Retry").props.onClick();
  view = h.render();
  assert.equal(calls, 2);
  assert.equal(find(view, (n) => n.props?.role === "alert"), undefined);
  assert.equal(find(view, (n) => n.type === "link" && n.props.children === "Open tree →").props.to, "/tree/saved");
  const deletion = find(view, (n) => n.type === "button" && n.props.children === "Delete tree");
  assert.match(deletion.props["aria-label"], /Example.*2026.*saved/);
  h.unmount();
});

test("focus trapping keeps its position on rerender, uses the latest Escape callback, and suspends when hidden", (t) => {
  const document = new EventTarget();
  globalValue(t, "document", document);
  let firstFocus = 0, lastFocus = 0, restored = 0, oldEscape = 0, newEscape = 0;
  const previous = { focus() { restored++; document.activeElement = this; } };
  const first = { focus() { firstFocus++; document.activeElement = this; } };
  const last = { focus() { lastFocus++; document.activeElement = this; } };
  const node = { querySelector: () => first, querySelectorAll: () => [first, last], contains: (el) => el === first || el === last };
  document.activeElement = previous;
  const h = harness("lib/useFocusTrap.ts", {}, "useFocusTrap");
  const ref = { current: node };
  h.render(ref, () => oldEscape++, true);
  h.render(ref, () => newEscape++, true);
  assert.equal(firstFocus, 1);
  const key = (name, shiftKey = false) => {
    const event = new Event("keydown", { cancelable: true });
    Object.assign(event, { key: name, shiftKey });
    document.dispatchEvent(event);
    return event;
  };
  key("Escape");
  assert.deepEqual([oldEscape, newEscape], [0, 1]);
  document.activeElement = last;
  assert.equal(key("Tab").defaultPrevented, true);
  assert.equal(document.activeElement, first);
  key("Tab", true);
  assert.equal(lastFocus, 1);
  h.render(ref, () => newEscape++, false);
  assert.equal(restored, 1);
  key("Escape");
  assert.equal(newEscape, 1);
  h.unmount();
});

test("a person list remains searchable with its query intact while full details cover it", () => {
  const trapped = [];
  const h = harness("components/PersonDrawer.tsx", {
    "../lib/useFocusTrap": { useFocusTrap: (_ref, _close, active) => trapped.push(active) },
    "../lib/year": { formatYear: String }, "./AiOrigin": { AiMark: () => null },
  });
  const props = { title: "People", people: [{ xref: "a", name: "Annie" }, { xref: "b", name: "Bert", place: "York, England" }],
    searchable: true, onClose() {}, onViewTree() {} };
  let view = h.render(props);
  find(view, (n) => n.type === "input").props.onChange({ target: { value: "Bert" } });
  view = h.render({ ...props, hidden: true });
  assert.equal(view.props.hidden, true);
  assert.equal(view.props.style.display, "none");
  assert.equal(find(view, (n) => n.type === "input").props.value, "Bert");
  view = h.render(props);
  assert.equal(find(view, (n) => n.type === "input").props.value, "Bert");
  assert.equal(all(view, (n) => n.props?.className === "drill-row").length, 1);
  assert.deepEqual(trapped, [true, false, true]);
  const search = find(view, (n) => n.type === "input");
  assert.equal(search.props["aria-label"], "Search people or places");
  search.props.onChange({ target: { value: "  enGLand  " } });
  view = h.render(props);
  assert.equal(all(view, (n) => n.props?.className === "drill-row").length, 1);
  assert.ok(find(view, (n) => n.type === "span" && Array.isArray(n.props.children) &&
    n.props.children.includes("York, England")));
  find(view, (n) => n.type === "input").props.onChange({ target: { value: "Annie" } });
  view = h.render(props);
  assert.equal(all(view, (n) => n.props?.className === "drill-row").length, 1,
    "name search still finds a person without a recorded birthplace");
});

test("autofocused dialog fields keep focus, including when a different dialog opens", (t) => {
  const document = new EventTarget();
  globalValue(t, "document", document);
  let focused = 0;
  const search = { focus() { focused++; document.activeElement = this; } };
  const otherDialog = {};
  const node = { querySelector: () => search, contains: (el) => el === search };
  document.activeElement = search;
  const h = harness("lib/useFocusTrap.ts", {}, "useFocusTrap");
  const ref = { current: node };
  h.render(ref, () => {}, true);
  assert.equal(focused, 0, "a native autofocus field must not lose focus to the close button");
  document.activeElement = otherDialog;
  h.render(ref, () => {}, false);
  assert.equal(document.activeElement, otherDialog, "suspending a covered dialog must not steal focus");
  assert.equal(focused, 0);
  h.unmount();
});
