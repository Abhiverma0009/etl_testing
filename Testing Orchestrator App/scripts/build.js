/**
 * node-direct `next build` — run with `node scripts/build.js`.
 * Resolves Next's own CLI entry and spawns it via the running node.exe, so no
 * `next.cmd` / `npm.cmd` shim is needed (works on the locked-down VM).
 */
const { spawn } = require("child_process");
const path = require("path");

const nextBin = require.resolve("next/dist/bin/next");
const root = path.join(__dirname, "..");

const child = spawn(process.execPath, [nextBin, "build"], {
  cwd: root,
  stdio: "inherit",
});
child.on("exit", (code) => process.exit(code ?? 0));
