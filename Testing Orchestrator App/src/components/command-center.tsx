"use client";

import { useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { categoryLabel } from "@/lib/categories";
import { fixTips } from "@/lib/remediation";
import type { CheckResult, RunResult } from "@/lib/types";
import type { RunAnalytics } from "@/lib/runAnalytics";
import { fmtDateTime, fmtDuration } from "@/lib/format";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Loader2 } from "lucide-react";

const STATUS_COLOR: Record<string, string> = {
  PASS: "#12b76a",
  WARN: "#f79009",
  FAIL: "#f04438",
  ERROR: "#7a5af8",
  SKIPPED: "#667085",
};
const PILL: Record<string, { c: string; bg: string }> = {
  FAIL: { c: "#b42318", bg: "#fee4e2" },
  ERROR: { c: "#5925dc", bg: "#ece9fe" },
  WARN: { c: "#93540b", bg: "#fdf0d9" },
  PASS: { c: "#087443", bg: "#d9f5e6" },
  SKIPPED: { c: "#475467", bg: "#eef0f4" },
};
const ORDER: Record<string, number> = { FAIL: 0, ERROR: 1, WARN: 2, PASS: 3, SKIPPED: 4 };

// --- Metrics rendering -------------------------------------------------------
// Validator metrics are heterogeneous: scalars, string lists (e.g. missing
// columns), key→count maps (e.g. null_counts), and lists of per-row objects
// (e.g. null_handling column breakdown). Render each shape as readable text
// instead of raw JSON / arrays.
function humanizeKey(k: string): string {
  const s = k.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function fmtScalar(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return String(v);
    if (Number.isInteger(v)) return v.toLocaleString();
    const abs = Math.abs(v);
    if (abs !== 0 && abs < 0.0001) return v.toExponential(2);
    return String(parseFloat(v.toFixed(6)));
  }
  return String(v);
}

const isPrimitive = (v: unknown): boolean => v === null || typeof v !== "object";

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block max-w-full whitespace-normal break-words rounded bg-[#eef1f5] px-1.5 py-0.5 font-mono text-[11px] text-[#475467]">
      {children}
    </span>
  );
}

function MetricValue({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "")
    return <span className="text-[#98a2b3]">—</span>;

  if (typeof value === "number" || typeof value === "boolean" || typeof value === "string")
    return <span className="tabular-nums">{fmtScalar(value)}</span>;

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-[#98a2b3]">none</span>;
    // list of column names / primitives → chips
    if (value.every(isPrimitive))
      return (
        <div className="flex flex-wrap gap-1">
          {value.map((x, i) => (
            <Chip key={i}>{String(x)}</Chip>
          ))}
        </div>
      );
    // list of per-row objects → one compact "k: v · k: v" line each
    return (
      <div className="space-y-1">
        {value.map((row, i) => (
          <div key={i} className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px]">
            {Object.entries(row as Record<string, unknown>).map(([sk, sv]) => (
              <span key={sk}>
                <span className="text-[#98a2b3]">{humanizeKey(sk)}:</span>{" "}
                <span className="tabular-nums text-[#344054]">{fmtScalar(sv)}</span>
              </span>
            ))}
          </div>
        ))}
      </div>
    );
  }

  // plain object (key → scalar map, e.g. null_counts) → labelled chips
  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) return <span className="text-[#98a2b3]">none</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([sk, sv]) => (
        <Chip key={sk}>
          <span className="text-[#98a2b3]">{sk}</span>{" "}
          <span className="tabular-nums text-[#344054]">{fmtScalar(sv)}</span>
        </Chip>
      ))}
    </div>
  );
}

function MetricsView({ metrics }: { metrics: Record<string, unknown> }) {
  const entries = Object.entries(metrics ?? {}).filter(([, v]) => v !== undefined);
  if (entries.length === 0) return <span className="text-[#98a2b3]">—</span>;
  return (
    <div className="space-y-2">
      {entries.map(([k, v]) => (
        <div key={k} className="flex flex-col gap-1">
          <div className="text-[11.5px] font-medium text-[#667085]">
            {humanizeKey(k)}
          </div>
          <div className="min-w-0 text-[12px] leading-[1.6] text-[#344054]">
            <MetricValue value={v} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function CommandCenter({
  run,
  analytics,
  member,
}: {
  run: RunResult;
  analytics: RunAnalytics;
  member: string;
}) {
  const [status, setStatus] = useState<string>("All");
  const [cat, setCat] = useState<string | null>(null);

  const sorted = useMemo(
    () => [...run.checks].sort((a, b) => ORDER[a.status] - ORDER[b.status]),
    [run.checks],
  );
  const firstFail = sorted.find((c) => c.status === "FAIL" || c.status === "ERROR");
  const [open, setOpen] = useState<string | null>(firstFail ? checkKey(firstFail, 0) : null);

  // evidence preview
  const [preview, setPreview] = useState<{ columns: string[]; rows: string[][]; total: number; truncated: boolean } | null>(null);
  const [previewTitle, setPreviewTitle] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);

  async function viewEvidence(path: string, label: string) {
    setPreviewLoading(true);
    setPreviewTitle(label);
    setPreview(null);
    try {
      const res = await fetch(
        `/api/evidence/preview?member=${encodeURIComponent(member)}&runId=${encodeURIComponent(run.run_id)}&path=${encodeURIComponent(path)}`,
      );
      if (res.ok) setPreview(await res.json());
    } finally {
      setPreviewLoading(false);
    }
  }

  const c = run.counts;
  const feed = sorted
    .map((chk, i) => ({ chk, key: checkKey(chk, i) }))
    .filter(({ chk }) => (status === "All" || chk.status === status) && (!cat || chk.category === cat));

  const kpis = [
    { label: "PASS", value: c.PASS ?? 0, sub: `of ${c.TOTAL ?? 0} checks`, s: "PASS" },
    { label: "WARN", value: c.WARN ?? 0, sub: "within tolerance", s: "WARN" },
    { label: "FAIL", value: c.FAIL ?? 0, sub: `${analytics.p1FailCount} are P1`, s: "FAIL" },
    { label: "ERROR", value: c.ERROR ?? 0, sub: (c.ERROR ?? 0) ? "checks crashed" : "no crashes", s: "ERROR" },
    { label: "SKIPPED", value: c.SKIPPED ?? 0, sub: "not configured", s: "SKIPPED" },
  ];

  const chips = [
    { s: "All", label: `All ${c.TOTAL ?? 0}` },
    { s: "FAIL", label: `Fail ${c.FAIL ?? 0}` },
    { s: "WARN", label: `Warn ${c.WARN ?? 0}` },
    { s: "PASS", label: `Pass ${c.PASS ?? 0}` },
    { s: "SKIPPED", label: `Skipped ${c.SKIPPED ?? 0}` },
  ];

  const delta = analytics.deltaPts;
  const barSeg = analytics.bar;

  return (
    <div className="min-h-full bg-[#f7f8fa] px-7 pb-10 pt-6">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="text-[19px] font-bold text-[#101828]">Test Results Overview</div>
        <span className="rounded-[5px] bg-[#101828] px-2 py-[3px] font-mono text-[11px] font-medium text-white">
          {run.run_id}
        </span>
        <span className="text-[12px] text-[#667085]">
          {run.suite ?? "—"} · {run.source ?? "—"} → {run.target ?? "—"} · {fmtDateTime(run.started_at)} ·{" "}
          {fmtDuration(run.started_at, run.finished_at)}
        </span>
        <div className="ml-auto flex gap-2">
          <Link
            href="/runs"
            className="rounded-[7px] border border-[#d0d5dd] bg-white px-3.5 py-[7px] text-[12px] font-semibold text-[#344054] hover:bg-[#f7f8fa]"
          >
            All runs
          </Link>
          <a
            href={`/api/report/pdf?member=${encodeURIComponent(member)}&runId=${encodeURIComponent(run.run_id)}`}
            className="rounded-[7px] border border-[#d0d5dd] bg-white px-3.5 py-[7px] text-[12px] font-semibold text-[#344054] hover:bg-[#f7f8fa]"
          >
            Download PDF
          </a>
          <Link
            href="/runs/new"
            className="rounded-[7px] bg-[#2a5fdb] px-3.5 py-[7px] text-[12px] font-semibold text-white hover:bg-[#2250bd]"
          >
            New run
          </Link>
        </div>
      </div>

      {/* KPI strip */}
      <div className="mt-5 grid grid-cols-[1.4fr_repeat(5,1fr)] gap-3">
        <div className="rounded-[10px] bg-[#101828] px-[18px] py-4 text-white">
          <div className="text-[11px] tracking-[.08em] text-[#98a2b3]">PASS RATE</div>
          <div className="mt-1.5 flex items-baseline gap-2">
            <div className="text-[34px] font-bold leading-none">{analytics.passRate}%</div>
            {delta !== null && delta !== 0 ? (
              <div
                className="text-[11px] font-semibold"
                style={{ color: delta < 0 ? "#f97066" : "#32d583" }}
              >
                {delta < 0 ? "▼" : "▲"} {Math.abs(delta)} pts vs prev run
              </div>
            ) : (
              <div className="text-[11px] font-semibold text-[#98a2b3]">
                {analytics.prevRunId ? "no change vs prev run" : "first run"}
              </div>
            )}
          </div>
          <div className="mt-3 flex h-1.5 overflow-hidden rounded-[3px] bg-[#344054]">
            <div style={{ width: `${barSeg.pass}%`, background: "#12b76a" }} />
            <div style={{ width: `${barSeg.warn}%`, background: "#f79009" }} />
            <div style={{ width: `${barSeg.fail}%`, background: "#f04438" }} />
            <div style={{ width: `${barSeg.error}%`, background: "#7a5af8" }} />
            <div style={{ width: `${barSeg.skipped}%`, background: "#667085" }} />
          </div>
        </div>
        {kpis.map((k) => {
          const active = status === k.s;
          return (
            <button
              key={k.label}
              onClick={() => setStatus(active ? "All" : k.s)}
              className="rounded-[10px] border bg-white px-[18px] py-4 text-left hover:border-[#2a5fdb]"
              style={{ borderColor: active ? "#2a5fdb" : "#e6e8ee" }}
            >
              <div className="flex items-center gap-1.5 text-[11px] tracking-[.08em] text-[#667085]">
                <span className="h-2 w-2 rounded-full" style={{ background: STATUS_COLOR[k.label] }} />
                {k.label}
              </div>
              <div className="mt-1.5 text-[28px] font-bold leading-none" style={{ color: STATUS_COLOR[k.label] }}>
                {k.value}
              </div>
              <div className="mt-1.5 text-[11px] text-[#98a2b3]">{k.sub}</div>
            </button>
          );
        })}
      </div>

      {/* Triage + Category health */}
      <div className="mt-3 grid grid-cols-2 gap-3">
        {/* Failure triage */}
        <div className="rounded-[10px] border border-[#e6e8ee] bg-white px-[18px] py-4">
          <div className="flex items-baseline">
            <div className="text-[13px] font-semibold text-[#101828]">Failure triage</div>
            {analytics.prevRunId && (
              <div className="ml-auto text-[11px] text-[#98a2b3]">vs {analytics.prevRunId}</div>
            )}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2.5">
            <div className="rounded-lg border border-[#f4d1cd] bg-[#fff8f7] px-3.5 py-3">
              <div className="text-[11px] font-bold tracking-[.06em] text-[#b42318]">NEW THIS RUN</div>
              <div className="mt-1 text-[26px] font-bold leading-none text-[#b42318]">{analytics.newFailureCount}</div>
              <div className="mt-[5px] text-[11px] text-[#a05a52]">
                {analytics.newFailureLabels.slice(0, 6).join(" · ") || "None"}
              </div>
            </div>
            <div className="rounded-lg border border-[#e6e8ee] bg-[#f7f8fa] px-3.5 py-3">
              <div className="text-[11px] font-bold tracking-[.06em] text-[#667085]">RECURRING</div>
              <div className="mt-1 text-[26px] font-bold leading-none text-[#344054]">{analytics.recurringCount}</div>
              <div className="mt-[5px] text-[11px] text-[#98a2b3]">
                {analytics.oldestRecurringLabel
                  ? `Oldest: ${analytics.oldestRecurringLabel} — failing ${analytics.oldestRecurringStreak} runs`
                  : "No recurring failures"}
              </div>
            </div>
          </div>
          {analytics.p1FailCount > 0 && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-[#f4d1cd] bg-[#fef3f2] px-3 py-2.5">
              <span className="rounded-[4px] bg-[#d92d20] px-[7px] py-0.5 text-[10px] font-bold text-white">P1</span>
              <span className="text-[12px] font-medium text-[#912018]">
                {analytics.p1FailCount} P1 {analytics.signoffCategoryLabel ? `${analytics.signoffCategoryLabel} ` : ""}
                failure{analytics.p1FailCount === 1 ? "" : "s"} block sign-off
                {analytics.signoffTable ? ` on ${analytics.signoffTable}` : ""}
              </span>
              <button
                onClick={() => {
                  setStatus("FAIL");
                  setCat(null);
                }}
                className="ml-auto whitespace-nowrap text-[11.5px] font-semibold text-[#b42318]"
              >
                View →
              </button>
            </div>
          )}
        </div>

        {/* Category health */}
        <div className="rounded-[10px] border border-[#e6e8ee] bg-white px-[18px] py-4">
          <div className="text-[13px] font-semibold text-[#101828]">
            Category health <span className="font-normal text-[#98a2b3]">· click to filter feed</span>
          </div>
          <div className="mt-3 grid grid-cols-4 gap-2">
            {analytics.categoryHealth.map((ch) => {
              const active = cat === ch.id;
              const bg = active ? "#eef4ff" : ch.hasFail ? "#fff8f7" : "#fff";
              const border = active ? "#2a5fdb" : ch.hasFail ? "#f4d1cd" : "#e6e8ee";
              return (
                <button
                  key={ch.id}
                  onClick={() => setCat(active ? null : ch.id)}
                  className="rounded-lg border px-[11px] py-2.5 text-left hover:border-[#2a5fdb]"
                  style={{ background: bg, borderColor: border }}
                >
                  <div className="min-h-[28px] text-[11px] font-semibold leading-[1.25] text-[#344054]">
                    {ch.name}
                  </div>
                  <div className="mt-1.5 flex items-center gap-1.5">
                    <span className="h-[7px] w-[7px] rounded-full" style={{ background: ch.dot }} />
                    <span className="font-mono text-[10.5px] font-medium text-[#667085]">{ch.stat}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Check feed */}
      <div className="mt-3 overflow-hidden rounded-[10px] border border-[#e6e8ee] bg-white">
        <div className="flex flex-wrap items-center gap-2 border-b border-[#eef0f4] px-[18px] py-3.5">
          <div className="mr-1 text-[13px] font-semibold text-[#101828]">Checks</div>
          {chips.map((ch) => {
            const active = status === ch.s;
            return (
              <button
                key={ch.s}
                onClick={() => setStatus(ch.s)}
                className="rounded-full border px-[11px] py-[5px] text-[11.5px] font-semibold"
                style={{
                  color: active ? "#fff" : "#344054",
                  background: active ? "#2a5fdb" : "#fff",
                  borderColor: active ? "#2a5fdb" : "#d0d5dd",
                }}
              >
                {ch.label}
              </button>
            );
          })}
          {cat && (
            <button
              onClick={() => setCat(null)}
              className="rounded-full border border-[#b8cdf8] bg-[#eef4ff] px-[11px] py-[5px] text-[11.5px] font-semibold text-[#2a5fdb]"
            >
              {categoryLabel(cat)} ✕
            </button>
          )}
          <div className="ml-auto text-[11.5px] text-[#98a2b3]">
            {feed.length} of {c.TOTAL ?? 0} shown
          </div>
        </div>

        {feed.map(({ chk, key }) => {
          const isOpen = open === key;
          const p = PILL[chk.status] ?? PILL.SKIPPED;
          const tips = fixTips(chk.category, chk.status);
          const hasFix = tips.length > 0;
          const ev = chk.evidence?.[0];
          return (
            <div key={key} className="border-b border-[#f2f4f7]">
              <button
                onClick={() => setOpen(isOpen ? null : key)}
                className="flex w-full items-center gap-3 px-[18px] py-[11px] text-left hover:bg-[#fafbfc]"
              >
                <span
                  className="flex-none rounded-[5px] py-[3px] text-center text-[10px] font-bold tracking-[.05em]"
                  style={{ width: 58, color: p.c, background: p.bg }}
                >
                  {chk.status}
                </span>
                <span className="flex-none rounded-[4px] border border-[#e6e8ee] px-1.5 py-0.5 font-mono text-[10px] font-semibold text-[#667085]">
                  {chk.severity}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold text-[#101828]">
                    {chk.name}
                  </div>
                  <div className="mt-px text-[11px] text-[#98a2b3]">
                    {categoryLabel(chk.category)} · {chk.target_table ?? "—"}
                  </div>
                </div>
                <div className="hidden max-w-[340px] overflow-hidden text-ellipsis whitespace-nowrap text-[11.5px] text-[#667085] lg:block">
                  {chk.message}
                </div>
                <span className="flex-none text-[11px] text-[#98a2b3]">{isOpen ? "▲" : "▼"}</span>
              </button>

              {isOpen && (
                <div className="grid grid-cols-1 gap-3 px-[18px] pb-4 lg:grid-cols-[1fr_360px]">
                  {hasFix ? (
                    <div className="rounded-lg border border-[#efe3c2] bg-[#fbf7ec] px-4 py-3">
                      <div className="text-[11px] font-bold tracking-[.05em] text-[#8a6c1f]">POINTS TO FIX</div>
                      <div className="mt-1.5 text-[12px] leading-[1.6] text-[#5c4d1e]">{tips.join(" ")}</div>
                      {ev && (
                        <button
                          onClick={() => viewEvidence(ev.path, ev.label)}
                          className="mt-2.5 flex items-center gap-1.5 text-[11.5px] font-semibold text-[#8a6c1f]"
                        >
                          ⤓ Evidence CSV{ev.rows ? ` · ${ev.rows} rows` : ""}
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-lg border border-[#e6e8ee] bg-[#f7f8fa] px-4 py-3">
                      <div className="text-[11px] font-bold tracking-[.05em] text-[#667085]">RESULT</div>
                      <div className="mt-1.5 text-[12px] leading-[1.6] text-[#475467]">{chk.message}</div>
                    </div>
                  )}
                  <div className="rounded-lg border border-[#e6e8ee] bg-[#f7f8fa] px-4 py-3">
                    <div className="mb-2 text-[11px] font-bold tracking-[.05em] text-[#667085]">METRICS</div>
                    <MetricsView metrics={chk.metrics} />
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {feed.length === 0 && (
          <div className="px-7 py-7 text-center text-[12.5px] text-[#98a2b3]">
            No checks match the current filters.
          </div>
        )}
      </div>

      {/* Evidence preview dialog */}
      <Dialog open={previewLoading || preview !== null} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle className="font-mono text-sm">{previewTitle}</DialogTitle>
          </DialogHeader>
          {previewLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading…
            </div>
          ) : preview ? (
            <>
              <div className="max-h-[60vh] overflow-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {preview.columns.map((col) => (
                        <TableHead key={col} className="whitespace-nowrap">{col}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {preview.rows.map((row, ri) => (
                      <TableRow key={ri}>
                        {row.map((cell, ci) => (
                          <TableCell key={ci} className="whitespace-nowrap font-mono text-xs">
                            {cell}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {preview.truncated && (
                <p className="text-xs text-muted-foreground">
                  Showing first {preview.rows.length} of {preview.total} rows.
                </p>
              )}
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function checkKey(c: CheckResult, i: number): string {
  return `${c.rule_id || c.name}-${c.category}-${i}`;
}
