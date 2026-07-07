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

const app = next({ dev, dir: __dirname, hostname, port });
const handle = app.getRequestHandler();

app
  .prepare()
  .then(() => {
    createServer((req, res) => {
      handle(req, res, parse(req.url, true));
    }).listen(port, hostname, () => {
      // eslint-disable-next-line no-console
      console.log(`> ETL Test app ready on http://${hostname}:${port}`);
    });
  })
  .catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    process.exit(1);
  });
