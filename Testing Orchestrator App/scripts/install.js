/**
 * node-direct npm — run with `node scripts/install.js [npm args...]`.
 *   node scripts/install.js            -> npm install
 *   node scripts/install.js -D shadcn  -> npm install -D shadcn
 *
 * npm ships alongside node itself, so we resolve npm-cli.js relative to the
 * running node.exe and spawn it directly — no `npm.cmd` shim (works on the
 * locked-down VM). Portable across the dev machine and VM since it follows
 * whichever node.exe is executing.
 */
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

function resolveNpmCli() {
  const nodeDir = path.dirname(process.execPath);
  const candidates = [
    path.join(nodeDir, "node_modules", "npm", "bin", "npm-cli.js"),
    // Some installs place npm one level up (e.g. under a versioned dir).
    path.join(nodeDir, "..", "lib", "node_modules", "npm", "bin", "npm-cli.js"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  throw new Error(
    "Could not locate npm-cli.js next to node.exe (" + nodeDir + "). " +
    "Ensure this Node install bundles npm."
  );
}

const npmCli = resolveNpmCli();
const args = process.argv.slice(2);
const root = path.join(__dirname, "..");

const child = spawn(process.execPath, [npmCli, ...(args.length ? args : ["install"])], {
  cwd: root,
  stdio: "inherit",
});
child.on("exit", (code) => process.exit(code ?? 0));
