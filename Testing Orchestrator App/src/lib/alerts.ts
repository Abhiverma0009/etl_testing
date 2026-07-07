/**
 * Data-quality alerting (server-only). After a run finishes, evaluate the alert
 * rules in config/alerts.json against its result.json and, when triggered, POST a
 * summary to a Microsoft Teams channel via a Power Automate HTTP webhook. Every
 * evaluation that triggers is recorded to output/alerts.json so the /alerts page
 * (and the dashboard) can show them even if the webhook isn't configured.
 *
 * The webhook URL is read from an env var named by config (default
 * TEAMS_WEBHOOK_URL) and never stored in config or shown in the UI.
 */
import { promises as fs } from "node:fs";
import {
  ALERTS_PATH,
  ALERTS_LOG_PATH,
  TEAM_MEMBER,
  memberAlertsLogPath,
  encodeRunRef,
} from "./paths";
import { getRun, listTeamMembers } from "./runsStore";
import type { RunResult, CheckResult } from "./types";

export interface AlertConfig {
  enabled: boolean;
  /** Trigger when a check's status OR severity is in this list (e.g. ["FAIL","ERROR","P1"]). */
  on: string[];
  channel?: string; // informational label, e.g. "teams"
  webhookEnv: string; // env var holding the Power Automate URL
  suites?: string[] | null; // limit to these suite names (null/empty = all)
}

export interface AlertRecord {
  id: string;
  run_id: string;
  member: string; // whose run this alert is about
  run_ref: string; // "<member>~<run_id>" — matches ManifestEntry.run_ref for /runs links
  suite?: string | null;
  ts: string;
  triggered_by: string[]; // status/severity tokens that matched
  failed: number;
  errored: number;
  total: number;
  worst_severity: string | null;
  sample: { name: string; status: string; severity: string; message: string }[];
  webhook_configured: boolean;
  sent: boolean;
  send_error?: string;
}

const DEFAULT_CONFIG: AlertConfig = {
  enabled: false,
  on: ["FAIL", "ERROR", "P1"],
  channel: "teams",
  webhookEnv: "TEAMS_WEBHOOK_URL",
  suites: null,
};

export async function getAlertConfig(): Promise<AlertConfig> {
  try {
    const text = await fs.readFile(ALERTS_PATH, "utf-8");
    return { ...DEFAULT_CONFIG, ...(JSON.parse(text) as Partial<AlertConfig>) };
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return DEFAULT_CONFIG;
    throw err;
  }
}

export async function saveAlertConfig(cfg: AlertConfig): Promise<void> {
  await fs.writeFile(ALERTS_PATH, JSON.stringify(cfg, null, 2), "utf-8");
}

/** This machine's own alert log only (used when appending a new alert). */
async function listOwnAlerts(): Promise<AlertRecord[]> {
  try {
    const text = await fs.readFile(ALERTS_LOG_PATH, "utf-8");
    const data = JSON.parse(text) as { alerts?: AlertRecord[] };
    return data.alerts ?? [];
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
}

/** Team-wide alert history, merged across every member's alerts.json. */
export async function listAlerts(): Promise<AlertRecord[]> {
  const members = await listTeamMembers();
  const lists = await Promise.all(
    members.map(async (m) => {
      try {
        const text = await fs.readFile(memberAlertsLogPath(m), "utf-8");
        const data = JSON.parse(text) as { alerts?: AlertRecord[] };
        return data.alerts ?? [];
      } catch {
        // Missing or mid-sync on a teammate's OneDrive copy — skip for this read.
        return [];
      }
    }),
  );
  return lists.flat().sort((a, b) => (a.ts < b.ts ? 1 : -1));
}

async function appendAlert(rec: AlertRecord): Promise<void> {
  const existing = await listOwnAlerts();
  const alerts = [rec, ...existing].slice(0, 200);
  await fs.writeFile(ALERTS_LOG_PATH, JSON.stringify({ alerts }, null, 2), "utf-8");
}

const SEV_RANK: Record<string, number> = { P1: 4, P2: 3, P3: 2, P4: 1 };

function matches(check: CheckResult, on: string[]): boolean {
  return on.includes(check.status) || on.includes(check.severity);
}

function worstSeverity(checks: CheckResult[]): string | null {
  let best: string | null = null;
  for (const c of checks) {
    if (best === null || (SEV_RANK[c.severity] ?? 0) > (SEV_RANK[best] ?? 0)) best = c.severity;
  }
  return best;
}

/** Build the JSON payload posted to the Power Automate flow. */
function buildPayload(run: RunResult, rec: AlertRecord) {
  const title = `⚠️ ETL DQ Alert — ${run.suite ?? run.run_id} by ${rec.member} (${rec.failed} failed, ${rec.errored} error)`;
  const lines = rec.sample.map((s) => `• [${s.severity}] ${s.name}: ${s.message}`);
  return {
    title,
    text: lines.join("\n"),
    run_id: run.run_id,
    member: rec.member,
    suite: run.suite ?? null,
    target: run.target ?? null,
    failed: rec.failed,
    errored: rec.errored,
    total: rec.total,
    worst_severity: rec.worst_severity,
    triggered_by: rec.triggered_by,
    checks: rec.sample,
  };
}

/**
 * Evaluate a finished run and, if it trips the alert rules, record + send an alert.
 * Safe to call fire-and-forget; never throws.
 */
export async function evaluateAndAlert(runId: string | undefined): Promise<void> {
  try {
    if (!runId) return;
    const cfg = await getAlertConfig();
    if (!cfg.enabled) return;
    // This function only ever runs right after a run this machine itself
    // triggered, so the run lives under this machine's own member folder.
    const run = await getRun(TEAM_MEMBER, runId);
    if (!run) return;
    if (cfg.suites && cfg.suites.length && !cfg.suites.includes(run.suite ?? "")) return;

    const tripped = run.checks.filter((c) => matches(c, cfg.on));
    if (tripped.length === 0) return;

    const failed = run.checks.filter((c) => c.status === "FAIL").length;
    const errored = run.checks.filter((c) => c.status === "ERROR").length;
    const triggeredTokens = Array.from(
      new Set(cfg.on.filter((t) => run.checks.some((c) => c.status === t || c.severity === t))),
    );

    const url = process.env[cfg.webhookEnv];
    const rec: AlertRecord = {
      id: `${runId}-${Date.now()}`,
      run_id: runId,
      member: TEAM_MEMBER,
      run_ref: encodeRunRef(TEAM_MEMBER, runId),
      suite: run.suite,
      ts: new Date().toISOString(),
      triggered_by: triggeredTokens,
      failed,
      errored,
      total: run.checks.length,
      worst_severity: worstSeverity(tripped),
      sample: tripped.slice(0, 10).map((c) => ({
        name: c.name,
        status: c.status,
        severity: c.severity,
        message: c.message,
      })),
      webhook_configured: Boolean(url),
      sent: false,
    };

    if (url) {
      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildPayload(run, rec)),
        });
        rec.sent = resp.ok;
        if (!resp.ok) rec.send_error = `HTTP ${resp.status}`;
      } catch (e) {
        rec.send_error = String(e);
      }
    }

    await appendAlert(rec);
  } catch {
    // Never let alerting break a run.
  }
}
