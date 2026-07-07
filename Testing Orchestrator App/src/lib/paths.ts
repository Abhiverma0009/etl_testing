/**
 * Resolves the on-disk locations the app reads/writes. Driven by
 * Testing Orchestrator App/.env.local (REPO_ROOT / PYTHON_EXE / TEAM_*), with
 * sensible fallbacks so the app also works with no env file (repo root =
 * parent of this app folder).
 *
 * Team run sharing: every run this machine produces is written under
 * `${TEAM_RUNS_ROOT}/${TEAM_MEMBER}/...` — the exact same manifest.json +
 * runs/<id>/result.json shape as before, just nested one level under this
 * person's own name. Point TEAM_RUNS_ROOT at a folder synced by everyone's
 * OneDrive client (e.g. a shared Teams/SharePoint folder) and each teammate
 * only ever WRITES their own subfolder — no two machines ever write the same
 * file, so there is nothing for OneDrive's sync to race or corrupt. Reading
 * (see runsStore.ts / alerts.ts) scans every subfolder under TEAM_RUNS_ROOT
 * to build the merged team-wide view. With no env vars set, TEAM_RUNS_ROOT
 * defaults to the local `output/` folder and TEAM_MEMBER to the OS username,
 * so a solo setup behaves the same as before except for that one extra
 * nesting level.
 *
 * Server-only module (uses node:path / node:os). Do not import from client
 * components.
 */
import os from "node:os";
import path from "node:path";

export const REPO_ROOT =
  process.env.REPO_ROOT || path.resolve(process.cwd(), "..");

export const PYTHON_EXE =
  process.env.PYTHON_EXE ||
  path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");

export const CONFIG_DIR = path.join(REPO_ROOT, "config");
export const SUITES_DIR = path.join(CONFIG_DIR, "suites");
export const MAPPINGS_DIR = path.join(CONFIG_DIR, "mappings");
export const REPORTS_DIR = path.join(CONFIG_DIR, "reports");
export const CONNECTIONS_PATH = path.join(CONFIG_DIR, "connections.yaml");
export const ALERTS_PATH = path.join(CONFIG_DIR, "alerts.json");
export const SCENARIOS_PATH = path.join(CONFIG_DIR, "scenarios.yaml");

// This machine's identity within the shared run history. Defaults to the OS
// username so nothing needs configuring for a single person to get a stable,
// human-readable id; override in .env.local if two teammates share a username.
export const TEAM_MEMBER = process.env.TEAM_MEMBER || os.userInfo().username;

// The folder every teammate's per-person output subfolder lives under. Point
// this at a OneDrive-synced shared folder to enable team-wide run visibility;
// left unset, it's just the local output/ folder (single-machine behavior).
export const TEAM_RUNS_ROOT =
  process.env.TEAM_RUNS_ROOT || path.join(REPO_ROOT, "output");

/** Absolute path to a given team member's own output folder. */
export function memberDir(member: string): string {
  return path.join(TEAM_RUNS_ROOT, member);
}

// This machine's own output folder — the only one it ever writes to.
export const OUTPUT_DIR = memberDir(TEAM_MEMBER);
export const RUNS_DIR = path.join(OUTPUT_DIR, "runs");
export const MANIFEST_PATH = path.join(OUTPUT_DIR, "manifest.json");
export const ALERTS_LOG_PATH = path.join(OUTPUT_DIR, "alerts.json");
// Persisted scenario-run (batch) records for this machine's member.
export const SCENARIO_RUNS_DIR = path.join(OUTPUT_DIR, "scenario-runs");
// Ephemeral suites synthesized for one-click report runs (kept out of config/).
export const RUNSUITES_DIR = path.join(OUTPUT_DIR, ".runsuites");

export function memberManifestPath(member: string): string {
  return path.join(memberDir(member), "manifest.json");
}

export function memberAlertsLogPath(member: string): string {
  return path.join(memberDir(member), "alerts.json");
}

export function memberScenarioRunsDir(member: string): string {
  return path.join(memberDir(member), "scenario-runs");
}

export function memberRunDir(member: string, runId: string): string {
  return path.join(memberDir(member), "runs", runId);
}

export function memberResultJsonPath(member: string, runId: string): string {
  return path.join(memberRunDir(member, runId), "result.json");
}

/** Resolve an evidence path (stored relative to the run dir) to an absolute path. */
export function memberEvidenceAbsPath(
  member: string,
  runId: string,
  relPath: string,
): string {
  return path.join(memberRunDir(member, runId), relPath);
}

// --- Backward-compatible aliases for this machine's own (TEAM_MEMBER) paths ---
export function runDir(runId: string): string {
  return memberRunDir(TEAM_MEMBER, runId);
}

export function resultJsonPath(runId: string): string {
  return memberResultJsonPath(TEAM_MEMBER, runId);
}

export function evidenceAbsPath(runId: string, relPath: string): string {
  return memberEvidenceAbsPath(TEAM_MEMBER, runId, relPath);
}

/**
 * Composite run reference used in URLs/links so a run from any teammate's
 * folder can be addressed unambiguously: "<member>~<run_id>".
 */
export function encodeRunRef(member: string, runId: string): string {
  return `${member}~${runId}`;
}

export function decodeRunRef(ref: string): { member: string; runId: string } | null {
  const i = ref.indexOf("~");
  if (i <= 0 || i === ref.length - 1) return null;
  return { member: ref.slice(0, i), runId: ref.slice(i + 1) };
}
