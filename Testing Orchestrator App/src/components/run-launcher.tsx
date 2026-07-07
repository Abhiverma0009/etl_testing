"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2, Play, CheckCircle2 } from "lucide-react";
import { categoryLabel } from "@/lib/categories";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { StatusDot } from "@/components/status-badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface SuiteInfo {
  name: string;
  source: string | null;
  target: string;
  tests: string[];
}

type CatState = { status: "pending" | "running" | "done"; counts?: Record<string, number> };

export function RunLauncher({
  suites,
  categories,
  member,
}: {
  suites: SuiteInfo[];
  categories: string[];
  member: string;
}) {
  const router = useRouter();
  const [suiteName, setSuiteName] = useState<string>(suites[0]?.name ?? "");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [catState, setCatState] = useState<Record<string, CatState>>({});
  const esRef = useRef<EventSource | null>(null);

  const suite = suites.find((s) => s.name === suiteName);

  function toggle(cat: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }

  const doneCount = Object.values(catState).filter((c) => c.status === "done").length;
  const progressPct = total ? Math.round((doneCount / total) * 100) : 0;

  async function start() {
    if (!suiteName) return;
    setRunning(true);
    setRunId(null);
    setCatState({});
    setTotal(0);

    let res: Response;
    try {
      res = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          suiteName,
          tests: selected.size ? Array.from(selected) : undefined,
        }),
      });
    } catch (e) {
      setRunning(false);
      toast.error("Failed to start run: " + String(e));
      return;
    }

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setRunning(false);
      toast.error(data.error || `Failed to start (HTTP ${res.status})`);
      return;
    }

    const jobId = data.jobId as string;
    const es = new EventSource(`/api/runs/${jobId}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      let ev: Record<string, unknown>;
      try {
        ev = JSON.parse(e.data);
      } catch {
        return;
      }
      handleEvent(ev);
    };
    es.onerror = () => {
      // stream closed; job_end handler already covers completion
    };
  }

  function handleEvent(ev: Record<string, unknown>) {
    const type = ev.event as string;

    if (type === "run_start") {
      const cats = (ev.categories as string[]) ?? [];
      setTotal(cats.length);
      setRunId((ev.run_id as string) ?? null);
      const init: Record<string, CatState> = {};
      for (const c of cats) init[c] = { status: "pending" };
      setCatState(init);
    } else if (type === "category_start") {
      const c = ev.category as string;
      setCatState((s) => ({ ...s, [c]: { status: "running" } }));
    } else if (type === "category_complete") {
      const c = ev.category as string;
      setCatState((s) => ({
        ...s,
        [c]: { status: "done", counts: (ev.counts as Record<string, number>) ?? {} },
      }));
    } else if (type === "job_end") {
      esRef.current?.close();
      setRunning(false);
      const rid = (ev.run_id as string) ?? runId;
      const code = ev.exit_code as number | undefined;
      if (ev.error) {
        toast.error("Run failed to launch: " + String(ev.error));
      } else if (code === 2) {
        toast.error("Run finished with errors (a check could not run).");
      } else if (code === 1) {
        toast.warning("Run finished — some checks failed.");
      } else {
        toast.success("Run passed.");
      }
      if (rid) setTimeout(() => router.push(`/runs/${member}~${rid}`), 900);
    } else if (type === "error") {
      esRef.current?.close();
      setRunning(false);
      toast.error(String(ev.message ?? "Stream error"));
    }
  }

  const orderedCats =
    total > 0 ? Object.keys(catState) : selected.size ? Array.from(selected) : suite?.tests ?? [];

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Configure</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium">Suite</label>
            <Select value={suiteName} onValueChange={setSuiteName} disabled={running}>
              <SelectTrigger className="max-w-md">
                <SelectValue placeholder="Select a suite" />
              </SelectTrigger>
              <SelectContent>
                {suites.map((s) => (
                  <SelectItem key={s.name} value={s.name}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {suite && (
              <p className="mt-1.5 text-xs text-muted-foreground">
                {(suite.source ?? "—") + " → " + suite.target} · suite defines{" "}
                {suite.tests.length || "all"} test categor
                {suite.tests.length === 1 ? "y" : "ies"}
              </p>
            )}
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium">
              Categories{" "}
              <span className="font-normal text-muted-foreground">
                (leave all unchecked to use the suite&apos;s configured tests)
              </span>
            </label>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
              {categories.map((c) => (
                <label key={c} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={selected.has(c)}
                    onCheckedChange={() => toggle(c)}
                    disabled={running}
                  />
                  {categoryLabel(c)}
                </label>
              ))}
            </div>
          </div>

          <Button onClick={start} disabled={running || !suiteName}>
            {running ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-1.5 h-4 w-4" />
            )}
            {running ? "Running…" : "Run"}
          </Button>
        </CardContent>
      </Card>

      {(running || total > 0) && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-base">
              <span>Progress {runId ? <span className="font-mono text-xs text-muted-foreground">{runId}</span> : null}</span>
              <span className="text-sm font-normal text-muted-foreground">
                {doneCount}/{total || "?"} · {progressPct}%
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <div className="divide-y rounded-md border">
              {orderedCats.map((c) => {
                const st = catState[c];
                return (
                  <div key={c} className="flex items-center gap-3 px-3 py-2 text-sm">
                    <span className="w-4 shrink-0">
                      {st?.status === "running" ? (
                        <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      ) : st?.status === "done" ? (
                        <CheckCircle2 className="h-4 w-4 text-status-pass" />
                      ) : (
                        <span className="block h-2 w-2 rounded-full bg-muted-foreground/30" />
                      )}
                    </span>
                    <span className={cn("flex-1", !st && "text-muted-foreground")}>
                      {categoryLabel(c)}
                    </span>
                    {st?.counts && (
                      <span className="flex gap-2 text-xs text-muted-foreground">
                        {["PASS", "WARN", "FAIL", "ERROR", "SKIPPED"]
                          .filter((k) => st.counts![k])
                          .map((k) => (
                            <span key={k} className="inline-flex items-center gap-1">
                              <StatusDot status={k} />
                              {st.counts![k]}
                            </span>
                          ))}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
