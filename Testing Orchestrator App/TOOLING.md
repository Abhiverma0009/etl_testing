# Running this app without `.cmd` (locked-down VM)

The client VM blocks execution of `.cmd` files, so `npm run *` / `npx *` /
`next` (which resolve to `npm.cmd` / `npx.cmd` / `next.cmd` on Windows) cannot be
used there. Every operation below is invoked as **`node <script>.js`** instead —
a direct call to the `node.exe` binary, which is not a `.cmd` shim and is not
blocked. The same commands work on the dev machine and the VM.

> Spawning the Python test engine (`python.exe`) is likewise a direct binary
> call and is unaffected by the `.cmd` restriction.

## Commands

| Task | Command |
|------|---------|
| Start (dev) | `node server.js` |
| Start (prod) | `node scripts/build.js` then `set NODE_ENV=production & node server.js` |
| Build only | `node scripts/build.js` |
| Install deps | `node scripts/install.js` |
| Add a dep | `node scripts/install.js -D <pkg>` (or without `-D` for a runtime dep) |
| Add a shadcn component | `node scripts/install.js -D shadcn` (once), then `node scripts/add-component.js <name>` |

`server.js` uses Next's programmatic API with the default **webpack** bundler
(no Turbopack), avoiding the `lightningcss` native-binary problem entirely — and
this project pins **Next 14 + Tailwind v3**, which have no `lightningcss`
dependency at all.

## How it works

Windows resolves bare tool names (`npm`, `npx`, `next`) to `.cmd` wrappers. The
scripts here bypass those by resolving the tool's real `.js` entry point and
running it through the current `node.exe`:

- `install.js` finds `npm-cli.js` next to `process.execPath` (node ships npm).
- `build.js` resolves `next/dist/bin/next` and runs `next build`.
- `add-component.js` resolves the locally-installed `shadcn` CLI entry.

## Node on the VM

Install Node on the VM with its architecture-matched build (the normal MSI, or a
portable zip extracted anywhere — installing Node itself is not blocked; only
invoking tools via `.cmd` shims is).

### 32-bit VM: SWC native binary failure (hit on the real client VM)

On a 32-bit (`win32-ia32`) VM, `node server.js` failed with:

```
⚠ Attempted to load @next/swc-win32-ia32-msvc, but an error occurred: A dynamic
link library (DLL) initialization routine failed.
⨯ Failed to load SWC binary for win32/ia32
```

`npm` did install the matching native `@next/swc-win32-ia32-msvc` binary — it
just failed to *load* as a Windows DLL (classically a missing/mismatched MSVC
runtime). **That's not fixable here** — no admin rights on the client VM means
no Visual C++ Redistributable install. So instead of chasing the VM's system
libraries, the app is now configured to **never touch the native binary at
all** on a platform like this. Two changes, both already in this repo:

1. **`next.config.mjs`: `experimental.useWasmBinary: true`.** Read
   `next/dist/build/swc/index.js` directly to confirm this: Next hard-lists
   `"i686-pc-windows-msvc"` (32-bit Windows) in `knownDefaultWasmFallbackTriples`
   — its own set of platforms it expects to need the WASM compiler. Combined
   with `useWasmBinary: true`, Next tries the **WASM** compiler *first*, before
   ever attempting the native binary — so the DLL that fails to load is never
   touched, and Next's own runtime auto-downloader (which otherwise re-fetches
   a missing native binary over HTTP and would hit the exact same crash) never
   fires either. On a platform Next doesn't consider WASM-fallback-eligible
   (this dev machine's x64), the flag is a documented no-op — Next logs a
   notice and uses native as normal. **This is the fix that actually matters**;
   verified end-to-end on the dev machine (page compiles and serves via the
   same code path) since there's no 32-bit machine here to test on directly.
2. **`package.json`: `next` pinned to `14.2.33`, with `@next/swc-wasm-nodejs`
   pinned to the same version** so the WASM compiler is guaranteed present
   (Next stopped publishing `@next/swc-wasm-nodejs` after `14.2.33`, so this
   pin is required, not incidental). **`14.2.33` has a known CVE** (see
   `https://nextjs.org/blog/security-update-2025-12-11`); accepted deliberately
   because this app is **run only locally, never hosted** — that threat model
   doesn't apply. If that ever changes (the app gets deployed/exposed), revisit
   this pin and re-check whether a newer `next`/matching-`@next/swc-wasm-nodejs`
   pair is available.
3. **`.npmrc`: `omit=optional`.** Belt-and-suspenders: this stops `npm install`
   from ever pulling *any* platform's native `@next/swc-*` binary in the first
   place (they're all listed as `optionalDependencies` of `next` itself), so
   there's nothing broken sitting in `node_modules` to begin with, on any
   machine.

**On the VM:** delete `node_modules`, run `node scripts/install.js`, then
`node server.js` — no admin rights or system installs needed. First compile
under WASM is noticeably slower than native (expect it, not a hang); page
loads are otherwise unaffected.
