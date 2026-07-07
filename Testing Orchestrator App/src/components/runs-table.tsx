"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { ManifestEntry } from "@/lib/types";
import { StatusBadge, StatusDot } from "@/components/status-badge";
import { fmtDateTime } from "@/lib/format";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const STATUS_KEYS = ["PASS", "WARN", "FAIL", "ERROR", "SKIPPED"] as const;

function CountsCell({ counts }: { counts: Partial<Record<string, number>> }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {STATUS_KEYS.map((k) =>
        counts[k] ? (
          <span key={k} className="inline-flex items-center gap-1 text-muted-foreground">
            <StatusDot status={k} />
            {counts[k]}
          </span>
        ) : null,
      )}
    </div>
  );
}

type RunRow = ManifestEntry & { scenarioName?: string | null };

export function RunsTable({ runs }: { runs: RunRow[] }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"all" | "pass" | "fail">("all");

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    return runs.filter((r) => {
      if (status === "pass" && !r.passed) return false;
      if (status === "fail" && r.passed) return false;
      if (!query) return true;
      return [r.run_id, r.member, r.scenarioName, r.suite, r.category, r.source, r.target]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
  }, [runs, q, status]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search runs…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="h-9 max-w-xs"
        />
        <div className="flex gap-1">
          {(["all", "pass", "fail"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                status === s
                  ? "border-primary bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <span className="ml-auto text-xs text-muted-foreground">
          {filtered.length} of {runs.length}
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-24">Result</TableHead>
              <TableHead>Run</TableHead>
              <TableHead>Member</TableHead>
              <TableHead>Scenario</TableHead>
              <TableHead>Suite / Category</TableHead>
              <TableHead>Source → Target</TableHead>
              <TableHead>Checks</TableHead>
              <TableHead className="text-right">Started</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((r) => (
              <TableRow
                key={r.run_ref}
                className="cursor-pointer"
                onClick={() => router.push(`/runs/${r.run_ref}`)}
              >
                <TableCell>
                  <StatusBadge status={r.passed ? "PASS" : "FAIL"} />
                </TableCell>
                <TableCell className="font-mono text-xs">{r.run_id}</TableCell>
                <TableCell className="text-sm">{r.member}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{r.scenarioName || "—"}</TableCell>
                <TableCell className="text-sm">{r.suite || r.category || "—"}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {(r.source || "—") + " → " + (r.target || "—")}
                </TableCell>
                <TableCell>
                  <CountsCell counts={r.counts} />
                </TableCell>
                <TableCell className="text-right text-xs text-muted-foreground">
                  {fmtDateTime(r.started_at)}
                </TableCell>
              </TableRow>
            ))}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="py-10 text-center text-sm text-muted-foreground">
                  No runs match the filter.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
