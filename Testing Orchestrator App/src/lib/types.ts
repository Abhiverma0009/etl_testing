// Shapes mirroring the Python engine's result.json and the on-disk config files.

export type Status = "PASS" | "FAIL" | "WARN" | "ERROR" | "SKIPPED";

export interface Evidence {
  label: string;
  path: string; // relative to the run dir (e.g. "evidence/rule_BR001.csv")
  rows?: number | null;
}

export interface CheckResult {
  name: string;
  category: string;
  status: Status;
  severity: string; // P1..P4
  target_table?: string | null;
  message: string;
  metrics: Record<string, unknown>;
  sample: Record<string, unknown>[];
  sample_columns: string[];
  evidence: Evidence[];
  duration_s: number;
  rule_id?: string | null;
  use_case?: string | null;
}

export interface Counts {
  PASS: number;
  FAIL: number;
  WARN: number;
  ERROR: number;
  SKIPPED: number;
  TOTAL: number;
}

export interface RunResult {
  run_id: string;
  started_at: string;
  finished_at?: string | null;
  category?: string | null;
  suite?: string | null;
  source?: string | null;
  target?: string | null;
  mapping_file?: string | null;
  host?: string;
  meta?: Record<string, unknown>;
  expected?: string; // "pass" (default) or "fail" for a negative/detection test
  counts: Counts;
  passed: boolean;
  checks: CheckResult[];
}

export interface ManifestEntry {
  run_id: string;
  started_at: string;
  finished_at?: string | null;
  passed: boolean | null;
  counts: Partial<Counts>;
  source?: string | null;
  target?: string | null;
  suite?: string | null;
  category?: string | null;
  categories?: string[]; // test categories this run executed (from result.json meta)
  path: string; // e.g. "runs/<id>/result.json"
  member: string; // team member (folder) this run belongs to
  run_ref: string; // "<member>~<run_id>" — unambiguous id for /runs/[runId] links
}

export interface Manifest {
  generated: string;
  count: number;
  shown: number;
  runs: ManifestEntry[];
}

// ---- config ----
export type ConnectionType = "access" | "snowflake" | "sqlserver" | "files" | "sqlite";

export interface ConnectionConfig {
  name: string;
  type: ConnectionType;
  [key: string]: unknown; // type-specific fields; secrets kept as literal "${VAR}"
}

export type SuiteTableEntry = string | { name: string; options?: Record<string, unknown> };

export interface SuiteConfig {
  name: string; // filename stem
  connections?: string;
  mapping?: string;
  source?: string | null;
  target: string;
  options?: Record<string, unknown>;
  tests?: string[];
  tables?: SuiteTableEntry[];
  reports?: string[]; // report ids (config/reports/<id>.json) run by the `report` category
  scenario?: string; // id of the test scenario this suite (test case) belongs to
  expected?: string; // "fail" marks a negative test case (expected to detect a failure)
}

// ---- scenarios (a test scenario groups multiple suites = test cases) ----
export interface Scenario {
  id: string; // key in config/scenarios.yaml
  name: string;
  description?: string;
}

export interface ScenarioRunCase {
  suite: string; // suite (test case) name
  status: "pending" | "running" | "done" | "error";
  run_id?: string | null;
  run_ref?: string | null; // "<member>~<run_id>" for linking to the run detail
  passed?: boolean | null;
  counts?: Partial<Counts>;
  exit_code?: number | null;
  error?: string | null;
}

export interface ScenarioRunRecord {
  batch_id: string;
  scenario_id: string;
  scenario_name: string;
  member: string;
  started_at: string;
  finished_at?: string | null;
  status: "running" | "passed" | "failed" | "error";
  cases: ScenarioRunCase[];
  rollup: {
    cases_total: number;
    cases_passed: number;
    cases_failed: number;
    cases_errored: number;
  };
}
