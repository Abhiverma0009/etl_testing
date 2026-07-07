/**
 * Run history store (server-only). Reads the same files the Python engine
 * writes — manifest.json (index) and runs/<id>/result.json (full detail),
 * plus evidence CSVs — but now scoped per team member and merged across all
 * of them, so everyone sees everyone's runs even though each person's app
 * instance only ever writes its own subfolder (see paths.ts for why that
 * split is what makes OneDrive-shared storage safe).
 */
import { promises as fs } from "node:fs";
import { parse as parseCsv } from "csv-parse/sync";
import {
  TEAM_MEMBER,
  TEAM_RUNS_ROOT,
  memberManifestPath,
  memberResultJsonPath,
  memberEvidenceAbsPath,
  encodeRunRef,
  decodeRunRef,
} from "./paths";
import type { Manifest, ManifestEntry, RunResult } from "./types";

/** Every team member with a folder under TEAM_RUNS_ROOT, plus this machine's
 * own member id even if it hasn't produced a run yet. */
export async function listTeamMembers(): Promise<string[]> {
  let entries: string[] = [];
  try {
    const dirents = await fs.readdir(TEAM_RUNS_ROOT, { withFileTypes: true });
    entries = dirents.filter((d) => d.isDirectory()).map((d) => d.name);
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
  }
  if (!entries.includes(TEAM_MEMBER)) entries.push(TEAM_MEMBER);
  return entries.sort();
}

async function readMemberManifest(member: string): Promise<ManifestEntry[]> {
  try {
    const text = await fs.readFile(memberManifestPath(member), "utf-8");
    const m = JSON.parse(text) as { runs?: Omit<ManifestEntry, "member" | "run_ref">[] };
    return (m.runs ?? []).map((r) => ({
      ...r,
      member,
      run_ref: encodeRunRef(member, r.run_id),
    }));
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    // A teammate's OneDrive copy mid-sync (partial/locked file) shouldn't break
    // the whole team view — skip it for this read, it'll show up once synced.
    return [];
  }
}

/** Merged, newest-first manifest across every team member's folder. */
export async function getManifest(): Promise<Manifest> {
  const members = await listTeamMembers();
  const lists = await Promise.all(members.map(readMemberManifest));
  const runs = lists.flat().sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
  return { generated: new Date().toISOString(), count: runs.length, shown: runs.length, runs };
}

export async function getRun(member: string, runId: string): Promise<RunResult | null> {
  try {
    const text = await fs.readFile(memberResultJsonPath(member, runId), "utf-8");
    return JSON.parse(text) as RunResult;
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}

/** Convenience: resolve a "<member>~<run_id>" ref (see paths.ts) in one call. */
export async function getRunByRef(ref: string): Promise<RunResult | null> {
  const parsed = decodeRunRef(ref);
  if (!parsed) return null;
  return getRun(parsed.member, parsed.runId);
}

/** Read an evidence CSV and return header + rows (capped for preview). */
export interface EvidenceTable {
  columns: string[];
  rows: string[][];
  total: number;
  truncated: boolean;
}

export async function readEvidenceCsv(
  member: string,
  runId: string,
  relPath: string,
  limit = 500,
): Promise<EvidenceTable> {
  const abs = memberEvidenceAbsPath(member, runId, relPath);
  const text = await fs.readFile(abs, "utf-8");
  const records = parseCsv(text, {
    skip_empty_lines: true,
    relax_column_count: true,
  }) as string[][];
  if (records.length === 0) return { columns: [], rows: [], total: 0, truncated: false };
  const [columns, ...body] = records;
  const truncated = body.length > limit;
  return {
    columns,
    rows: truncated ? body.slice(0, limit) : body,
    total: body.length,
    truncated,
  };
}

export function evidenceFileAbsPath(member: string, runId: string, relPath: string): string {
  return memberEvidenceAbsPath(member, runId, relPath);
}

/** Flatten all evidence across recent runs, across all team members. */
export interface EvidenceRow {
  member: string;
  run_id: string;
  run_ref: string;
  suite?: string | null;
  category: string;
  check_name: string;
  status: string;
  target_table?: string | null;
  label: string;
  path: string;
  rows?: number | null;
}

export async function listAllEvidence(): Promise<EvidenceRow[]> {
  const manifest = await getManifest();
  const out: EvidenceRow[] = [];
  for (const entry of manifest.runs) {
    const run = await getRun(entry.member, entry.run_id);
    if (!run) continue;
    for (const chk of run.checks) {
      for (const ev of chk.evidence ?? []) {
        out.push({
          member: entry.member,
          run_id: run.run_id,
          run_ref: entry.run_ref,
          suite: run.suite,
          category: chk.category,
          check_name: chk.name,
          status: chk.status,
          target_table: chk.target_table,
          label: ev.label,
          path: ev.path,
          rows: ev.rows,
        });
      }
    }
  }
  return out;
}

export type { Manifest, ManifestEntry, RunResult };
