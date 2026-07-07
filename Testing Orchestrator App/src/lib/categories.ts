// Ported verbatim from etl_test/reporting/dashboard.py (retired).
// Status palette + category labels. Keep in sync with globals.css --status-* vars.

export type Status = "PASS" | "FAIL" | "WARN" | "ERROR" | "SKIPPED";

export const STATUS_COLORS: Record<Status, string> = {
  PASS: "#1a7f4b",
  FAIL: "#c53030",
  WARN: "#b7791f",
  ERROR: "#6b46c1",
  SKIPPED: "#64748b",
};

export const STATUS_TINTS: Record<Status, string> = {
  PASS: "#e7f5ee",
  FAIL: "#fdecec",
  WARN: "#fdf3e2",
  ERROR: "#f0ebfa",
  SKIPPED: "#eef1f5",
};

export const STATUS_ORDER: Status[] = ["PASS", "WARN", "FAIL", "ERROR", "SKIPPED"];

export const CATEGORY_LABELS: Record<string, string> = {
  row_count: "Row / Record Count",
  schema: "Schema & Structure",
  datatype: "Data Type & Format",
  completeness: "Completeness",
  business_rules: "Business Rules",
  referential_integrity: "Referential Integrity",
  transformation: "Transformation Accuracy",
  historical: "Historical Integrity",
  deduplication: "Deduplication",
  null_handling: "Null / Default Handling",
  reconciliation: "Reconciliation & Variance",
  lineage: "Lineage & Traceability",
  incremental: "Incremental Load",
  cross_source: "Cross-Source Consistency",
  report: "Report Validation (GVC / MD&A)",
  gvc_report: "GVC Report Data Layer",
};

export const ALL_CATEGORIES = Object.keys(CATEGORY_LABELS);

export function categoryLabel(id: string): string {
  return CATEGORY_LABELS[id] ?? id;
}

export function statusColor(s: string): string {
  return STATUS_COLORS[s as Status] ?? "#64748b";
}

export function statusTint(s: string): string {
  return STATUS_TINTS[s as Status] ?? "#eef1f5";
}
