const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
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

function nodes(node, expandComponents = false) {
  if (Array.isArray(node)) return node.flatMap((child) => nodes(child, expandComponents));
  if (!node || typeof node !== "object") return [];
  const children = expandComponents && typeof node.type === "function"
    ? node.type(node.props) : node.props?.children ?? node.children;
  return [node, ...nodes(children, expandComponents)];
}
const find = (node, predicate) => nodes(node).find(predicate);
const text = (node) => [node?.props?.children].flat(Infinity)
  .map((child) => typeof child === "object" ? text(child) : child ?? "").join("");

// shortcut: renders are explicit and have no DOM; use browser checks for scheduling and layout.
function harness(source, mocks = {}, { exported = "default", beforeEffects } = {}) {
  const react = mocks.react ?? { memo: (component) => component,
    createContext: () => ({ Provider: "provider" }) };
  const slots = [];
  let cursor = 0, pending = [];
  const changed = (old, next) => !old || !next || old.length !== next.length ||
    old.some((value, i) => !Object.is(value, next[i]));
  const hooks = {
    useState(initial) {
      const i = cursor++;
      slots[i] ??= { value: typeof initial === "function" ? initial() : initial };
      return [slots[i].value, (value) => {
        slots[i].value = typeof value === "function" ? value(slots[i].value) : value;
      }];
    },
    useRef(initial) { return slots[cursor++] ??= { current: initial }; },
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
  Object.assign(react, hooks);
  const Component = typeof source === "function" ? source : load(source, { ...mocks, react })[exported];
  return {
    react,
    render(...args) {
      Object.assign(react, hooks);
      cursor = 0;
      pending = [];
      const tree = Component(...args);
      beforeEffects?.(tree);
      for (const { i } of pending) slots[i]?.cleanup?.();
      for (const { i, effect, deps } of pending) slots[i] = { deps, cleanup: effect() };
      return tree;
    },
    unmount() { for (const slot of slots) slot?.cleanup?.(); },
  };
}

const flush = () => new Promise(setImmediate);
function globalValue(t, name, value) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
  t.after(() => previous ? Object.defineProperty(globalThis, name, previous) : delete globalThis[name]);
}

module.exports = { load, nodes, find, text, harness, flush, globalValue };
