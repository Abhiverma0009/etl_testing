// Ported verbatim from etl_test/reporting/dashboard.py (retired).
// "Points to fix" guidance shown on non-passing checks, keyed by category.

export const REMEDIATION: Record<string, string[]> = {
  row_count: [
    "Check the pipeline's source query/filters — a WHERE clause or date window may be dropping rows.",
    "Confirm no duplicate ingestion (extra rows) or failed/rejected batches (missing rows).",
    "Reconcile counts per fund/period to locate exactly which partition is off.",
  ],
  schema: [
    "Align the target DDL with the mapping: add the missing column(s) or update the mapping.",
    "For extra unmapped columns (WARN), add them to the Columns sheet or confirm they are intentional (e.g. lineage).",
    "Re-deploy the affected table via the approved CI/CD pipeline, then re-run.",
  ],
  datatype: [
    "Fix the cast/parse in the transformation so numbers/dates aren't loaded as text.",
    "Check source formats (thousands separators, date patterns, locale) and the load's type handling.",
    "Verify the target column's declared type matches the mapping's target_datatype.",
  ],
  completeness: [
    "Populate the mandatory column upstream, or correct the mapping if it is genuinely nullable.",
    "For missing expected values (periods/files): confirm every source file/partition was ingested.",
    "For forbidden values present (e.g. CO2): add the exclusion filter to the ingestion pipeline.",
  ],
  business_rules: [
    "Open the evidence CSV to see the exact offending keys and values.",
    "Fix the transformation logic that sets the value (e.g. flag override, adjustment code, split/combine).",
    "If the rule is wrong or outdated, update it in the mapping's business rules and re-run.",
  ],
  referential_integrity: [
    "Load the missing parent rows first, or correct the child's foreign-key value.",
    "Check load ordering — the child table may have loaded before its parent dimension.",
    "Investigate null foreign keys separately; they indicate missing source linkage.",
  ],
  transformation: [
    "Compare source vs target for the flagged columns in the evidence CSV to see the derivation error.",
    "Review the transformation expression / FX-rate lookup / derived-flag logic for that column.",
    "Confirm the rate or reference data used for the correct period.",
  ],
  historical: [
    "Historical rows must be immutable — ensure the load only appends the current period.",
    "Investigate any late-arriving corrections; if legitimate, snapshot a new baseline.",
    "For missing periods, confirm the full history was migrated (no truncated date range).",
  ],
  deduplication: [
    "Review the Silver/Gold dedup logic (dedup key, window, ordering).",
    "Check for the same source record arriving from multiple feeds or a re-processed file.",
    "Use the evidence CSV to see which business keys are duplicated.",
  ],
  null_handling: [
    "A null must not become 0 — fix any COALESCE/default that overwrites true nulls (critical for FMV).",
    "Confirm intentional defaults are correct and only applied where the mapping specifies.",
    "Use the evidence CSV to see rows where source was null but target is zero.",
  ],
  reconciliation: [
    "Start with source-only (missing) and target-only (extra) rows — these are load-coverage issues.",
    "For value mismatches, drill into the per-column counts to see which field drifted.",
    "For aggregate-variance breaches, sum the column on both sides to locate the contributing rows.",
  ],
  lineage: [
    "Ensure the pipeline stamps audit columns (SOURCE_SYSTEM, LOAD_TIMESTAMP, BATCH_ID) on every row.",
    "Add the lineage columns to the target table if they are missing from the schema.",
    "For non-lineage tables (dimensions), set lineage_columns: [] in that table's options.",
  ],
  incremental: [
    "Existing rows changed unexpectedly — restrict the delta to new/updatable keys only.",
    "If columns are legitimately updatable, list them in incremental.updatable_columns.",
    "Investigate disappeared keys; set allow_deletes only if deletions are expected.",
  ],
  cross_source: [
    "Reconcile the two sources for the disagreeing keys in the evidence CSV.",
    "Normalise coding conventions across sources (e.g. 'Realised' vs 'R') via the mapping.",
    "Decide the system of record for the conflicting field and align the pipeline to it.",
  ],
  gvc_report: [
    "Compare the report's dataset query against the Gold table query — check joins, filters, grouping.",
    "For measure breaches, verify aggregation logic (SUM/AVG) and any report-side calculations.",
    "Confirm the report reads the current Gold layer, not a cached/older dataset.",
  ],
};

export const ERROR_TIPS: string[] = [
  "This check could not run (it errored) — read the message for the cause.",
  "Common causes: a connection/credential problem, a missing column referenced by config, or an invalid filter expression.",
  "Fix the underlying config/connection and re-run; an ERROR is not a data verdict.",
];

export function fixTips(category: string, status: string): string[] {
  if (status === "ERROR") return ERROR_TIPS;
  if (status === "FAIL" || status === "WARN") return REMEDIATION[category] ?? [];
  return [];
}
