/**
 * Cross-run analytics for the Command Center run-detail view (server-only).
 * Computes everything the design needs beyond a single result.json: pass-rate
 * delta vs the previous run, new-vs-recurring failures, failure streaks, the P1
 * sign-off blocker, category health, and the status bar segments — all derived
 * from the existing run history (manifest + prior result.json files).
 */
import { getManifest, getRun } from "./runsStore";
import { categoryLabel } from "./categories";
import type { CheckResult, Counts, RunResult } from "./types";

const PRIOR_RUNS_SCANNED = 12; // depth for streak computation

export interface CategoryHealth {
  id: string;
  name: string;
  pass: number;
  fail: number;
  warn: number;
  error: number;
  skipped: number;
  dot: string;
  hasFail: boolean;
  stat: string;
}

export interface RunAnalytics {
  passRate: number; // 0..100
  prevRunId: string | null;
  deltaPts: number | null; // passRate - prevPassRate
  bar: { pass: number; warn: number; fail: number; skipped: number; error: number }; // % 0..100
  p1FailCount: number;
  signoffTable: string | null;
  signoffCategoryLabel: string | null;
  newFailureLabels: string[];
  newFailureCount: number;
  recurringCount: number;
  oldestRecurringLabel: string | null;
  oldestRecurringStreak: number;
  categoryHealth: CategoryHealth[];
}

const STATUS_DOT: Record<string, string> = {
  FAIL: "#f04438",
  ERROR: "#7a5af8",
  WARN: "#f79009",
  PASS: "#12b76a",
  SKIPPED: "#98a2b3",
};

function checkId(c: CheckResult): string {
  return c.rule_id || `${c.category}|${c.name}|${c.target_table ?? ""}`;
}

/** Short human label for a check, used in the triage lists. */
function checkLabel(c: CheckResult): string {
  if (c.rule_id) return c.rule_id;
  return c.name.replace(/\s*\[[^\]]*\]\s*$/, "").trim();
}

function passRateOf(counts?: Partial<Counts>): number {
  const total = counts?.TOTAL ?? 0;
  if (!total) return 0;
  return Math.round(((counts?.PASS ?? 0) / total) * 100);
}

function statusMap(run: RunResult): Map<string, string> {
  const m = new Map<string, string>();
  for (const c of run.checks) m.set(checkId(c), c.status);
  return m;
}

export async function getRunAnalytics(run: RunResult): Promise<RunAnalytics> {
  const counts = run.counts;
  const total = counts.TOTAL || 1;
  const passRate = passRateOf(counts);

  // Status bar segments (% of total), order: pass, warn, fail, error, skipped.
  const bar = {
    pass: ((counts.PASS ?? 0) / total) * 100,
    warn: ((counts.WARN ?? 0) / total) * 100,
    fail: ((counts.FAIL ?? 0) / total) * 100,
    error: ((counts.ERROR ?? 0) / total) * 100,
    skipped: ((counts.SKIPPED ?? 0) / total) * 100,
  };

  // Prior runs of the same suite, newest-first (excluding this run), across
  // every team member — a suite's trend should track regardless of who ran it.
  const manifest = await getManifest();
  const prior = manifest.runs.filter(
    (r) => r.run_id !== run.run_id && r.suite === run.suite && (r.started_at ?? "") < (run.started_at ?? ""),
  );

  const prevRunId = prior[0]?.run_id ?? null;
  const deltaPts = prevRunId ? passRate - passRateOf(prior[0]?.counts) : null;

  // Load prev run's check statuses for new-vs-recurring; and a window of prior
  // runs (in order) for streak computation.
  const prevRun = prior[0] ? await getRun(prior[0].member, prior[0].run_id) : null;
  const prevMap = prevRun ? statusMap(prevRun) : null;

  const priorMaps: Map<string, string>[] = [];
  for (const entry of prior.slice(0, PRIOR_RUNS_SCANNED)) {
    const r = await getRun(entry.member, entry.run_id);
    if (r) priorMaps.push(statusMap(r));
  }

  const currentFails = run.checks.filter((c) => c.status === "FAIL" || c.status === "ERROR");

  const newFailures: CheckResult[] = [];
  const recurring: CheckResult[] = [];
  for (const c of currentFails) {
    const prevStatus = prevMap?.get(checkId(c));
    if (prevMap && (prevStatus === "FAIL" || prevStatus === "ERROR")) recurring.push(c);
    else newFailures.push(c);
  }

  // Streak: consecutive prior runs (newest-first) where this check also failed.
  function streak(c: CheckResult): number {
    let n = 1; // this run
    for (const m of priorMaps) {
      const s = m.get(checkId(c));
      if (s === "FAIL" || s === "ERROR") n += 1;
      else break;
    }
    return n;
  }

  let oldestRecurringLabel: string | null = null;
  let oldestRecurringStreak = 0;
  for (const c of recurring) {
    const s = streak(c);
    if (s > oldestRecurringStreak) {
      oldestRecurringStreak = s;
      oldestRecurringLabel = checkLabel(c);
    }
  }

  // P1 sign-off blocker.
  const p1Fails = currentFails.filter((c) => c.severity === "P1");
  const p1Tables = new Set(p1Fails.map((c) => c.target_table).filter(Boolean));
  const p1Cats = new Set(p1Fails.map((c) => c.category));
  const signoffTable = p1Tables.size === 1 ? (p1Fails.find((c) => c.target_table)?.target_table ?? null) : null;
  const signoffCategoryLabel = p1Cats.size === 1 ? categoryLabel([...p1Cats][0]) : null;

  // Category health.
  const catIds = [...new Set(run.checks.map((c) => c.category))];
  const categoryHealth: CategoryHealth[] = catIds.map((id) => {
    const items = run.checks.filter((c) => c.category === id);
    const n = (s: string) => items.filter((c) => c.status === s).length;
    const fail = n("FAIL") + n("ERROR");
    const warn = n("WARN");
    const pass = n("PASS");
    const skipped = n("SKIPPED");
    const dot = fail ? "#f04438" : warn ? "#f79009" : pass ? "#12b76a" : "#98a2b3";
    const stat =
      `${pass}✓ ${fail}✗` + (warn ? ` ${warn}⚠` : "") + (skipped ? ` ${skipped}–` : "");
    return { id, name: categoryLabel(id), pass, fail, warn, error: n("ERROR"), skipped, dot, hasFail: fail > 0, stat };
  });

  return {
    passRate,
    prevRunId,
    deltaPts,
    bar,
    p1FailCount: p1Fails.length,
    signoffTable,
    signoffCategoryLabel,
    newFailureLabels: newFailures.map(checkLabel),
    newFailureCount: newFailures.length,
    recurringCount: recurring.length,
    oldestRecurringLabel,
    oldestRecurringStreak,
    categoryHealth,
  };
}

export { STATUS_DOT };
