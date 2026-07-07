/**
 * Manages spawned Python test runs and fans their progress out to SSE clients.
 * Server-only, single-process (this is a local single-user tool).
 *
 * The Python CLI generates the real run_id, so we key jobs by our own jobId
 * (returned to the client immediately) and learn the run_id from the first
 * `run_start` progress event. The job map lives on globalThis so it survives
 * Next dev's module hot-reloads within the same Node process.
 */
import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";
import type { ChildProcess } from "node:child_process";
import { spawnEtl } from "./python";
import { OUTPUT_DIR, TEAM_MEMBER, encodeRunRef } from "./paths";
import { evaluateAndAlert } from "./alerts";
import { writeScenarioRun } from "./scenarioRunsStore";
import type { Counts, ScenarioRunRecord } from "./types";

export interface ProgressEvent {
  event: string;
  [key: string]: unknown;
}

interface Job {
  id: string;
  child: ChildProcess;
  emitter: EventEmitter;
  buffer: ProgressEvent[];
  done: boolean;
  runId?: string;
  resultPath?: string;
  exitCode?: number;
  passed?: boolean;
  counts?: Partial<Counts>;
  error?: string;
  suiteName?: string;
  startedAt: number;
}

interface Batch {
  id: string;
  emitter: EventEmitter;
  buffer: ProgressEvent[];
  done: boolean;
  record: ScenarioRunRecord;
}

interface JobStore {
  jobs: Map<string, Job>;
  batches: Map<string, Batch>;
}

const g = globalThis as unknown as { __etlJobStore?: JobStore };
const store: JobStore =
  g.__etlJobStore ?? (g.__etlJobStore = { jobs: new Map(), batches: new Map() });
if (!store.batches) store.batches = new Map(); // survive an older hot-reloaded store shape

export function isAnyBatchActive(): boolean {
  for (const b of store.batches.values()) if (!b.done) return true;
  return false;
}

export function isAnyRunActive(): boolean {
  for (const j of store.jobs.values()) if (!j.done) return true;
  return isAnyBatchActive();
}

export interface StartRunOptions {
  suitePath: string;
  suiteName?: string;
  tests?: string[];
  tables?: string[];
}

export function startRun(opts: StartRunOptions): string {
  const id = randomUUID();
  const args = ["run", "--suite", opts.suitePath, "--output", OUTPUT_DIR];
  if (opts.tests?.length) args.push("--tests", opts.tests.join(","));
  for (const t of opts.tables ?? []) args.push("--table", t);

  const child = spawnEtl({ args, progress: true });
  const emitter = new EventEmitter();
  emitter.setMaxListeners(0);

  const job: Job = {
    id,
    child,
    emitter,
    buffer: [],
    done: false,
    suiteName: opts.suiteName,
    startedAt: Date.now(),
  };
  store.jobs.set(id, job);

  const push = (ev: ProgressEvent) => {
    job.buffer.push(ev);
    emitter.emit("event", ev);
  };

  let stdoutBuf = "";
  child.stdout?.on("data", (chunk: Buffer) => {
    stdoutBuf += chunk.toString();
    let nl: number;
    while ((nl = stdoutBuf.indexOf("\n")) >= 0) {
      const line = stdoutBuf.slice(0, nl).trim();
      stdoutBuf = stdoutBuf.slice(nl + 1);
      if (!line.startsWith("{")) continue;
      try {
        const ev = JSON.parse(line) as ProgressEvent;
        if (ev.event === "run_start" && typeof ev.run_id === "string") {
          job.runId = ev.run_id;
        }
        if (ev.event === "run_complete") {
          if (typeof ev.run_id === "string") job.runId = ev.run_id;
          if (typeof ev.result_path === "string") job.resultPath = ev.result_path;
          if (typeof ev.passed === "boolean") job.passed = ev.passed;
          if (ev.counts && typeof ev.counts === "object") job.counts = ev.counts as Partial<Counts>;
        }
        push(ev);
      } catch {
        // ignore non-JSON lines (e.g. the CLI's human summary)
      }
    }
  });

  let stderrTail = "";
  child.stderr?.on("data", (chunk: Buffer) => {
    stderrTail = (stderrTail + chunk.toString()).slice(-4000);
  });

  const finalize = () => {
    if (job.done) return;
    job.done = true;
    push({
      event: "job_end",
      run_id: job.runId,
      result_path: job.resultPath,
      exit_code: job.exitCode,
      error: job.error,
      stderr_tail: job.error || job.exitCode ? stderrTail : undefined,
    });
    emitter.emit("end");
    // Fire-and-forget DQ alert evaluation (reads the freshly-written result.json).
    void evaluateAndAlert(job.runId);
    // Keep the finished job briefly so late reconnects can replay, then GC.
    setTimeout(() => store.jobs.delete(id), 5 * 60_000);
  };

  child.on("error", (err) => {
    job.error = String(err);
    finalize();
  });
  child.on("close", (code) => {
    job.exitCode = code ?? -1;
    finalize();
  });

  return id;
}

export function getJob(id: string) {
  return store.jobs.get(id);
}

export function getBatch(id: string) {
  return store.batches.get(id);
}

export interface ScenarioCase {
  suiteName: string;
  suitePath: string;
}

export interface StartScenarioOptions {
  scenarioId: string;
  scenarioName: string;
  cases: ScenarioCase[];
}

/**
 * Run every test case (suite) in a scenario **sequentially** — the engine
 * serializes runs anyway (Access/Jet single-reader) — continuing past failures.
 * Each case is a normal per-suite run (reusing startRun, so live progress, the
 * result.json, and DQ alerting all behave exactly as a manual run). A
 * ScenarioRunRecord is persisted and updated as each case completes.
 */
export function startScenarioRun(opts: StartScenarioOptions): string {
  const batchId = randomUUID();
  const emitter = new EventEmitter();
  emitter.setMaxListeners(0);

  const record: ScenarioRunRecord = {
    batch_id: batchId,
    scenario_id: opts.scenarioId,
    scenario_name: opts.scenarioName,
    member: TEAM_MEMBER,
    started_at: new Date().toISOString(),
    status: "running",
    cases: opts.cases.map((c) => ({ suite: c.suiteName, status: "pending" })),
    rollup: { cases_total: opts.cases.length, cases_passed: 0, cases_failed: 0, cases_errored: 0 },
  };

  const batch: Batch = { id: batchId, emitter, buffer: [], done: false, record };
  store.batches.set(batchId, batch);

  const push = (ev: ProgressEvent) => {
    batch.buffer.push(ev);
    emitter.emit("event", ev);
  };

  const persist = () => {
    void writeScenarioRun({ ...record, cases: [...record.cases] });
  };

  push({ event: "batch_start", batch_id: batchId, scenario_id: opts.scenarioId,
         scenario_name: opts.scenarioName, cases: opts.cases.map((c) => c.suiteName) });
  persist();

  const runAt = (i: number): void => {
    if (i >= opts.cases.length) {
      record.finished_at = new Date().toISOString();
      record.status = record.rollup.cases_errored ? "error"
        : record.rollup.cases_failed ? "failed" : "passed";
      persist();
      batch.done = true;
      push({ event: "batch_complete", batch_id: batchId, status: record.status,
             rollup: record.rollup });
      emitter.emit("end");
      setTimeout(() => store.batches.delete(batchId), 5 * 60_000);
      return;
    }

    const c = opts.cases[i];
    record.cases[i].status = "running";
    persist();
    push({ event: "case_start", batch_id: batchId, index: i, suite: c.suiteName });

    const jobId = startRun({ suitePath: c.suitePath, suiteName: c.suiteName });
    const job = store.jobs.get(jobId);
    if (!job) { // spawn failed to register — mark errored and move on
      record.cases[i] = { suite: c.suiteName, status: "error", error: "failed to start" };
      record.rollup.cases_errored += 1;
      persist();
      push({ event: "case_complete", batch_id: batchId, index: i, suite: c.suiteName,
             status: "error" });
      runAt(i + 1);
      return;
    }

    // Forward this case's granular progress onto the batch stream (scoped).
    const onEvent = (ev: ProgressEvent) =>
      push({ ...ev, batch_id: batchId, case_index: i, case_suite: c.suiteName, scoped: true });
    job.emitter.on("event", onEvent);

    job.emitter.once("end", () => {
      job.emitter.off("event", onEvent);
      const j = store.jobs.get(jobId);
      const errored = Boolean(j?.error) || j?.exitCode === 2;
      const passed = !errored && (j?.passed ?? j?.exitCode === 0);
      record.cases[i] = {
        suite: c.suiteName,
        status: errored ? "error" : "done",
        run_id: j?.runId ?? null,
        run_ref: j?.runId ? encodeRunRef(TEAM_MEMBER, j.runId) : null,
        passed,
        counts: j?.counts,
        exit_code: j?.exitCode ?? null,
        error: j?.error ?? null,
      };
      if (errored) record.rollup.cases_errored += 1;
      else if (passed) record.rollup.cases_passed += 1;
      else record.rollup.cases_failed += 1;
      persist();
      push({ event: "case_complete", batch_id: batchId, index: i, suite: c.suiteName,
             status: record.cases[i].status, passed, run_id: j?.runId,
             run_ref: record.cases[i].run_ref });
      runAt(i + 1);
    });
  };

  runAt(0);
  return batchId;
}
