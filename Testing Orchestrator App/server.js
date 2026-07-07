/**
 * Custom Node server for the ETL Test app.
 *
 * Runs the Next.js app via the programmatic API so the app can be launched with
 * a plain `node server.js` — no `next` / `npm` / `.cmd` shim involved. This is
 * what makes it runnable on the locked-down client VM that blocks `.cmd`
 * execution. Uses Next's default webpack bundler (no Turbopack).
 *
 *   Dev:  node server.js
 *   Prod: (after `node scripts/build.js`)  set NODE_ENV=production & node server.js
 */
const { createServer } = require("http");
const { parse } = require("url");
const next = require("next");
 
// Ensure cwd is the app dir regardless of how we're launched, so tooling that
// resolves config relative to cwd (postcss -> tailwind.config.ts) works.
process.chdir(__dirname);
 
const dev = process.env.NODE_ENV !== "production";
const hostname = process.env.HOST || "127.0.0.1";
const port = parseInt(process.env.PORT || "3000", 10);
 
// Prime the Next SWC loader with the WASM binding on 32-bit Windows BEFORE Next
// makes its own first binding request.
//
// Why this is needed: `experimental.useWasmBinary` in next.config.mjs is only
// honored by the loadBindings() calls that actually forward the flag (e.g.
// webpack-config). But Next's *first* SWC call during startup — the lightningcss
// capability probe in next/dist/server/config.js — calls loadBindings() with no
// argument, i.e. the native-first path. loadBindings() caches its result, so
// that first native-first call wins and the config flag never takes effect.
//
// On x64 the native-first path degrades gracefully to WASM when no native
// @next/swc binary is installed (which is our case — see .npmrc `omit=optional`),
// so it "just works" on the dev machine. On 32-bit Windows (ia32) the same
// native-first path instead hard-crashes the process with an access violation
// (exit 0xC0000005) before it can fall back. Calling loadBindings(true) here
// first populates the shared binding cache with the WASM implementation, so
// every later loadBindings() call — flag or not — reuses it and never touches
// the crashing native path. See Testing Orchestrator App/TOOLING.md.
async function primeWasmBindings() {
  if (process.platform !== "win32" || process.arch !== "ia32") return;
  const { loadBindings } = require("next/dist/build/swc");
  await loadBindings(true);
}
 
primeWasmBindings()
  .then(() => {
    const app = next({ dev, dir: __dirname, hostname, port });
    const handle = app.getRequestHandler();
    return app.prepare().then(() => {
      createServer((req, res) => {
        handle(req, res, parse(req.url, true));
      }).listen(port, hostname, () => {
        // eslint-disable-next-line no-console
        console.log(`> ETL Test app ready on http://${hostname}:${port}`);
      });
    });
  })
  .catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    process.exit(1);
  });
 
 