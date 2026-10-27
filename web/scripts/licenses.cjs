const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const lock = JSON.parse(fs.readFileSync(path.join(root, "package-lock.json"), "utf8"));
const notices = ["Family Tree — licenses for the browser bundle\n",
  fs.readFileSync(path.join(root, "..", "LICENSE"), "utf8")];
for (const [location, entry] of Object.entries(lock.packages)) {
  if (!location || entry.dev) continue;
  const directory = path.join(root, location);
  const pkg = JSON.parse(fs.readFileSync(path.join(directory, "package.json"), "utf8"));
  const files = fs.readdirSync(directory).filter((name) => /^(licen[cs]e|copying)([.\-_]|$)/i.test(name));
  if (!files.length) throw new Error(`No license file found for ${pkg.name}`);
  notices.push(`\n===== ${pkg.name} ${pkg.version} (${pkg.license}) =====\n`);
  for (const file of files) notices.push(fs.readFileSync(path.join(directory, file), "utf8"));
}
fs.mkdirSync(path.join(root, "public"), { recursive: true });
fs.writeFileSync(path.join(root, "public", "third-party-licenses.txt"), notices.join("\n"));
