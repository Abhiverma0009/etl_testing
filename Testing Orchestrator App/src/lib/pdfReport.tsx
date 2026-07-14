/**
 * Run detail → PDF (server-only). Produces a self-contained evidence document
 * for attaching to Jira tickets: run metadata, KPI summary, and the full check
 * list with metrics/messages/evidence file references. Deliberately text-first
 * (no charts/lineage graph) so it renders fast and prints cleanly.
 */
import React from "react";
import { Document, Page, Text, View, StyleSheet, renderToBuffer } from "@react-pdf/renderer";
import { categoryLabel, statusColor } from "./categories";
import { fmtDateTime, fmtDuration, fmtMetric } from "./format";
import type { CheckResult, RunResult } from "./types";
import type { RunAnalytics } from "./runAnalytics";

const ORDER: Record<string, number> = { FAIL: 0, ERROR: 1, WARN: 2, PASS: 3, SKIPPED: 4 };

const styles = StyleSheet.create({
  page: { padding: 32, fontSize: 9, fontFamily: "Helvetica", color: "#101828" },
  title: { fontSize: 16, fontWeight: 700, marginBottom: 2 },
  subtitle: { fontSize: 9, color: "#475467", marginBottom: 14 },
  metaRow: { flexDirection: "row", flexWrap: "wrap", marginBottom: 14, gap: 4 },
  metaItem: { width: "33%", marginBottom: 6 },
  metaLabel: { fontSize: 7.5, color: "#667085", textTransform: "uppercase", letterSpacing: 0.5 },
  metaValue: { fontSize: 9.5, fontWeight: 700, marginTop: 1 },
  kpiRow: { flexDirection: "row", gap: 6, marginBottom: 16 },
  kpiBox: { flex: 1, borderWidth: 1, borderColor: "#e4e7ec", borderRadius: 4, padding: 8 },
  kpiLabel: { fontSize: 7.5, color: "#667085" },
  kpiValue: { fontSize: 15, fontWeight: 700, marginTop: 2 },
  sectionTitle: { fontSize: 11, fontWeight: 700, marginTop: 10, marginBottom: 6 },
  checkCard: { borderWidth: 1, borderColor: "#e4e7ec", borderRadius: 4, padding: 8, marginBottom: 6, breakInside: "avoid" },
  checkHeader: { flexDirection: "row", alignItems: "center", marginBottom: 4 },
  statusPill: { fontSize: 7.5, fontWeight: 700, color: "#ffffff", paddingVertical: 2, paddingHorizontal: 6, borderRadius: 3, marginRight: 6 },
  checkName: { fontSize: 10, fontWeight: 700, flexGrow: 1 },
  checkMeta: { fontSize: 7.5, color: "#667085" },
  message: { fontSize: 8.5, marginBottom: 3, color: "#344054" },
  metricLine: { fontSize: 8, color: "#475467", marginBottom: 1 },
  evidenceLine: { fontSize: 7.5, color: "#667085", marginTop: 2 },
  footer: { position: "absolute", bottom: 16, left: 32, right: 32, fontSize: 7.5, color: "#98a2b3", textAlign: "center" },
});

function flattenMetrics(metrics: Record<string, unknown>): string[] {
  return Object.entries(metrics ?? {})
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => {
      const label = k.replace(/_/g, " ").toUpperCase();
      if (Array.isArray(v)) return `${label}: ${v.map((x) => fmtMetric(x)).join(", ")}`;
      if (typeof v === "object") return `${label}: ${fmtMetric(v)}`;
      return `${label}: ${fmtMetric(v)}`;
    });
}

function CheckCard({ chk }: { chk: CheckResult }) {
  const metricLines = flattenMetrics(chk.metrics).slice(0, 12);
  return (
    <View style={styles.checkCard} wrap={false}>
      <View style={styles.checkHeader}>
        <Text style={[styles.statusPill, { backgroundColor: statusColor(chk.status) }]}>{chk.status}</Text>
        <Text style={styles.checkName}>{chk.name}</Text>
        <Text style={styles.checkMeta}>
          {categoryLabel(chk.category)} · {chk.severity} · {chk.duration_s?.toFixed?.(2) ?? chk.duration_s}s
        </Text>
      </View>
      {chk.target_table ? <Text style={styles.checkMeta}>Table: {chk.target_table}</Text> : null}
      <Text style={styles.message}>{chk.message || "—"}</Text>
      {metricLines.map((line, i) => (
        <Text key={i} style={styles.metricLine}>• {line}</Text>
      ))}
      {chk.evidence?.length ? (
        <Text style={styles.evidenceLine}>
          Evidence: {chk.evidence.map((e) => e.label || e.path).join(", ")}
        </Text>
      ) : null}
    </View>
  );
}

function RunReportDocument({ run, analytics, member }: { run: RunResult; analytics: RunAnalytics; member: string }) {
  const sorted = [...run.checks].sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  const c = run.counts;
  const generatedAt = fmtDateTime(new Date().toISOString());

  return (
    <Document>
      <Page size="A4" style={styles.page} wrap>
        <Text style={styles.title}>ETL Test Run Report</Text>
        <Text style={styles.subtitle}>
          Run {run.run_id} · generated {generatedAt}
        </Text>

        <View style={styles.metaRow}>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Suite</Text>
            <Text style={styles.metaValue}>{run.suite ?? "—"}</Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Source → Target</Text>
            <Text style={styles.metaValue}>{run.source ?? "—"} → {run.target ?? "—"}</Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Team member</Text>
            <Text style={styles.metaValue}>{member}</Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Started</Text>
            <Text style={styles.metaValue}>{fmtDateTime(run.started_at)}</Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Duration</Text>
            <Text style={styles.metaValue}>{fmtDuration(run.started_at, run.finished_at)}</Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Overall result</Text>
            <Text style={[styles.metaValue, { color: run.passed ? "#12b76a" : "#f04438" }]}>
              {run.passed ? "PASSED" : "FAILED"}
            </Text>
          </View>
        </View>

        <View style={styles.kpiRow}>
          {(["PASS", "WARN", "FAIL", "ERROR", "SKIPPED"] as const).map((s) => (
            <View key={s} style={styles.kpiBox}>
              <Text style={styles.kpiLabel}>{s}</Text>
              <Text style={[styles.kpiValue, { color: statusColor(s) }]}>{c[s] ?? 0}</Text>
            </View>
          ))}
          <View style={styles.kpiBox}>
            <Text style={styles.kpiLabel}>PASS RATE</Text>
            <Text style={styles.kpiValue}>{analytics.passRate}%</Text>
          </View>
        </View>

        <Text style={styles.sectionTitle}>Checks ({sorted.length})</Text>
        {sorted.map((chk, i) => (
          <CheckCard key={`${chk.name}-${i}`} chk={chk} />
        ))}

        <Text
          style={styles.footer}
          render={({ pageNumber, totalPages }) => `Page ${pageNumber} of ${totalPages} · ${run.run_id}`}
          fixed
        />
      </Page>
    </Document>
  );
}

export async function renderRunReportPdf(
  run: RunResult,
  analytics: RunAnalytics,
  member: string,
): Promise<Buffer> {
  return renderToBuffer(<RunReportDocument run={run} analytics={analytics} member={member} />);
}
