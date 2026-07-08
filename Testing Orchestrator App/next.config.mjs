/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // Makes Next try the WASM SWC compiler BEFORE ever attempting the native
    // binary, on platforms Next already treats as WASM-fallback candidates
    // (next/dist/build/swc/index.js: knownDefaultWasmFallbackTriples includes
    // "i686-pc-windows-msvc" — 32-bit Windows). Without this, a native-binary
    // load failure that isn't a plain "not installed" error (e.g. the DLL
    // failing to initialize, seen on the restricted client VM) skips straight
    // to a hard crash — Next never falls back to WASM on its own in that case.
    // On any platform Next doesn't consider WASM-fallback-eligible (this dev
    // machine's x64), this is a documented no-op: Next logs a notice and uses
    // the native binary as normal. See Testing Orchestrator App/TOOLING.md.
    useWasmBinary: true,
  },
  webpack: (config, { dev }) => {
    if (dev) {
      // Webpack's default dev cache (PackFileCacheStrategy) gzip-serializes large
      // packs to .next/cache on disk. On this OneDrive-synced, AV/DLP-scanned VM
      // that buffer allocation fails ("RangeError: Array buffer allocation
      // failed") and crashes the dev server via an unhandledRejection. Use the
      // in-memory cache instead: no disk serialization, and there's ample RAM.
      config.cache = { type: "memory" };
    }
    return config;
  },
};
 
export default nextConfig;
 
 