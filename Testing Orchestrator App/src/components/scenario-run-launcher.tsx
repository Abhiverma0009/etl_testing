"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { Loader2, Play, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type CaseState = {
  suite: string;
  status: "pending" | "running" | "done" | "error";
  passed?: boolean;
  run_ref?: string | null;
};

export function ScenarioRunLauncher({
  scenarioId,
  suites,
}: {
  scenarioId: string;
  suites: string[];
}) {
  const router = useRouter();
  const [running, setRunning] = useState(false);
  const [cases, setCases] = useState<CaseState[]>(
    suites.map((s) => ({ suite: s, status: "pending" })),
  );
  const [rollup, setRollup] = useState<null | {
    cases_total: number;
    cases_passed: number;
    cases_failed: number;
    cases_errored: number;
  }>(null);
  const esRef = useRef<EventSource | null>(null);

  const done = cases.filter((c) => c.status === "done" || c.status === "error").length;
  const pct = suites.length ? Math.round((done / suites.length) * 100) : 0;

  function setCase(index: number, patch: Partial<CaseState>) {
    setCases((cs) => cs.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  }

  async function start() {
    if (suites.length === 0) return toast.error("This scenario has no test cases yet.");
    setRunning(true);
    setRollup(null);
    setCases(suites.map((s) => ({ suite: s, status: "pending" })));

    let res: Response;
    try {
      res = await fetch(`/api/scenarios/${encodeURIComponent(scenarioId)}/run`, {
        method: "POST",
      });
    } catch (e) {
      setRunning(false);
      return toast.error("Failed to start: " + String(e));
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setRunning(false);
      return toast.error(data.error || `Failed to start (HTTP ${res.status})`);
    }

    const es = new EventSource(`/api/scenarios/runs/${data.batchId}/stream`);
    esRef.current = es;
    es.onmessage = (e) => {
      let ev: Record<string, unknown>;
      try {
        ev = JSON.parse(e.data);
      } catch {
        return;
      }
      handle(ev);
    };
    es.onerror = () => {
      /* stream closes on batch_complete; handled there */
    };
  }

  function handle(ev: Record<string, unknown>) {
    const type = ev.event as string;
    if (type === "case_start") {
      setCase(ev.index as number, { status: "running" });
    } else if (type === "case_complete") {
      setCase(ev.index as number, {
        status: (ev.status as CaseState["status"]) ?? "done",
        passed: ev.passed as boolean | undefined,
        run_ref: (ev.run_ref as string) ?? null,
      });
    } else if (type === "batch_complete") {
      esRef.current?.close();
      setRunning(false);
      setRollup(ev.rollup as typeof rollup);
      const status = ev.status as string;
      if (status === "passed") toast.success("Scenario passed — all test cases passed.");
      else if (status === "error") toast.error("Scenario finished with errored case(s).");
      else toast.warning("Scenario finished — some test cases failed.");
      router.refresh();
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">
          Run scenario{" "}
          <span className="font-normal text-muted-foreground">
            ({suites.length} test case{suites.length === 1 ? "" : "s"}, sequential)
          </span>
        </CardTitle>
        <Button size="sm" onClick={start} disabled={running || suites.length === 0}>
          {running ? (
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-1.5 h-4 w-4" />
          )}
          {running ? "Running…" : "Run all"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {(running || done > 0) && (
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
          </div>
        )}
        <div className="divide-y rounded-md border">
          {cases.map((c, i) => (
            <div key={c.suite} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className="w-4 shrink-0">
                {c.status === "running" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                ) : c.status === "error" ? (
                  <AlertTriangle className="h-4 w-4 text-status-error" />
                ) : c.status === "done" ? (
                  c.passed ? (
                    <CheckCircle2 className="h-4 w-4 text-status-pass" />
                  ) : (
                    <XCircle className="h-4 w-4 text-status-fail" />
                  )
                ) : (
                  <span className="block h-2 w-2 rounded-full bg-muted-foreground/30" />
                )}
              </span>
              <span className={cn("flex-1 font-mono text-xs", c.status === "pending" && "text-muted-foreground")}>
                {i + 1}. {c.suite}
              </span>
              {c.run_ref ? (
                <Link href={`/runs/${c.run_ref}`} className="text-xs text-primary hover:underline">
                  view run
                </Link>
              ) : null}
            </div>
          ))}
        </div>
        {rollup && (
          <div className="text-sm text-muted-foreground">
            {rollup.cases_passed}/{rollup.cases_total} passed
            {rollup.cases_failed ? ` · ${rollup.cases_failed} failed` : ""}
            {rollup.cases_errored ? ` · ${rollup.cases_errored} errored` : ""}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
