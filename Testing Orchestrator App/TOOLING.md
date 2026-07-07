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
invoking tools via `.cmd` shims is). If the VM is 32-bit and `npm install` can't
fetch a matching Next SWC binary, pin a Next version known to ship
`@next/swc-win32-ia32-msvc`, or set the Babel fallback compiler. (Next 14 has
historically shipped ia32 SWC prebuilds.)
