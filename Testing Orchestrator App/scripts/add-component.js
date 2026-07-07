/**
 * node-direct shadcn component add — `node scripts/add-component.js <name...>`.
 * Only needed if you add shadcn/ui components while working directly on the
 * locked-down VM. Requires shadcn installed as a local devDependency first:
 *   node scripts/install.js -D shadcn
 */
const { spawn } = require("child_process");
const path = require("path");

let shadcnBin;
try {
  shadcnBin = require.resolve("shadcn/dist/index.js");
} catch {
  // eslint-disable-next-line no-console
  console.error(
    "shadcn is not installed locally. Run:  node scripts/install.js -D shadcn"
  );
  process.exit(1);
}

const args = process.argv.slice(2);
const root = path.join(__dirname, "..");
const child = spawn(process.execPath, [shadcnBin, "add", ...args, "-y", "-o"], {
  cwd: root,
  stdio: "inherit",
});
child.on("exit", (code) => process.exit(code ?? 0));
