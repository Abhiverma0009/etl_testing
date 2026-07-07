/**
 * Persisted scenario-run (batch) records (server-only). When a whole scenario is
 * run, one ScenarioRunRecord is written per batch under this machine's
 * <member>/scenario-runs/<batch_id>.json. Like runsStore/alerts, records are
 * member-scoped on write and merged across every TEAM_RUNS_ROOT member on read,
 * so the team sees each other's scenario runs. Single-writer-per-file (each
 * machine only writes its own member dir) keeps OneDrive sync safe.
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import { SCENARIO_RUNS_DIR, memberScenarioRunsDir } from "./paths";
import { listTeamMembers } from "./runsStore";
import type { ScenarioRunRecord } from "./types";

/** Write/overwrite this machine's own batch record. */
export async function writeScenarioRun(rec: ScenarioRunRecord): Promise<void> {
  await fs.mkdir(SCENARIO_RUNS_DIR, { recursive: true });
  const p = path.join(SCENARIO_RUNS_DIR, `${rec.batch_id}.json`);
  await fs.writeFile(p, JSON.stringify(rec, null, 2), "utf-8");
}

async function readMemberScenarioRuns(member: string): Promise<ScenarioRunRecord[]> {
  const dir = memberScenarioRunsDir(member);
  let files: string[] = [];
  try {
    files = (await fs.readdir(dir)).filter((f) => f.endsWith(".json"));
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
  const out: ScenarioRunRecord[] = [];
  for (const f of files) {
    try {
      out.push(JSON.parse(await fs.readFile(path.join(dir, f), "utf-8")) as ScenarioRunRecord);
    } catch {
      // partial/mid-sync file on a teammate's OneDrive copy — skip for this read
    }
  }
  return out;
}

/** All scenario-run records across every team member, newest first. */
export async function listScenarioRuns(): Promise<ScenarioRunRecord[]> {
  const members = await listTeamMembers();
  const lists = await Promise.all(members.map(readMemberScenarioRuns));
  return lists.flat().sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
}

export async function listScenarioRunsFor(scenarioId: string): Promise<ScenarioRunRecord[]> {
  return (await listScenarioRuns()).filter((r) => r.scenario_id === scenarioId);
}
