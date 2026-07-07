"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Plus, Link2, Unlink, Loader2 } from "lucide-react";
import { attachSuites, detachSuite } from "@/app/scenarios/actions";
import { StatusBadge } from "@/components/status-badge";
import { fmtDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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

export interface CaseRow {
  name: string;
  source: string | null;
  target: string;
  latest: { passed: boolean; started_at: string; run_ref: string } | null;
}

export interface AvailableSuite {
  name: string;
  scenarioName: string | null; // the scenario it's currently in, if any
}

export function ScenarioCasesManager({
  scenarioId,
  cases,
  available,
}: {
  scenarioId: string;
  cases: CaseRow[];
  available: AvailableSuite[];
}) {
  const [pending, startTransition] = useTransition();
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  function toggle(name: string) {
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(name)) n.delete(name);
      else n.add(name);
      return n;
    });
  }

  function attach() {
    if (picked.size === 0) return;
    startTransition(async () => {
      try {
        await attachSuites(scenarioId, Array.from(picked));
        toast.success(`Added ${picked.size} test case(s)`);
        setPicked(new Set());
        setOpen(false);
      } catch (e) {
        toast.error(String(e));
      }
    });
  }

  function detach(name: string) {
    if (!confirm(`Remove '${name}' from this scenario? The suite is kept (becomes Ungrouped).`)) return;
    startTransition(async () => {
      try {
        await detachSuite(name);
        toast.success(`Removed '${name}'`);
      } catch (e) {
        toast.error(String(e));
      }
    });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">
          Test cases <span className="font-normal text-muted-foreground">({cases.length})</span>
        </CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setOpen(true)} disabled={available.length === 0}>
            <Link2 className="mr-1.5 h-4 w-4" />
            Add existing
          </Button>
          <Button size="sm" asChild>
            <Link href={`/suites?newScenario=${encodeURIComponent(scenarioId)}`}>
              <Plus className="mr-1.5 h-4 w-4" />
              New test case
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Suite (test case)</TableHead>
                <TableHead>Source → Target</TableHead>
                <TableHead>Latest result</TableHead>
                <TableHead>Last run</TableHead>
                <TableHead className="w-16 text-right">Remove</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cases.map((c) => (
                <TableRow key={c.name}>
                  <TableCell className="font-mono text-xs">{c.name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {(c.source ?? "—") + " → " + c.target}
                  </TableCell>
                  <TableCell>
                    {c.latest ? (
                      <Link href={`/runs/${c.latest.run_ref}`}>
                        <StatusBadge status={c.latest.passed ? "PASS" : "FAIL"} />
                      </Link>
                    ) : (
                      <span className="text-xs text-muted-foreground">never run</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {c.latest ? fmtDateTime(c.latest.started_at) : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" onClick={() => detach(c.name)} disabled={pending}>
                      <Unlink className="h-4 w-4 text-status-fail" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {cases.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                    No test cases yet. Use <span className="font-medium">Add existing</span> or{" "}
                    <span className="font-medium">New test case</span>.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add existing test cases</DialogTitle>
            <DialogDescription>
              Pick suites to add to this scenario. A suite already in another scenario
              will be moved (a test case belongs to exactly one scenario).
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-80 space-y-1.5 overflow-y-auto py-2">
            {available.map((s) => (
              <label key={s.name} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted">
                <Checkbox checked={picked.has(s.name)} onCheckedChange={() => toggle(s.name)} />
                <span className="font-mono text-xs">{s.name}</span>
                {s.scenarioName ? (
                  <span className="ml-auto text-xs text-muted-foreground">in: {s.scenarioName} → move</span>
                ) : (
                  <span className="ml-auto text-xs text-muted-foreground">ungrouped</span>
                )}
              </label>
            ))}
            {available.length === 0 && (
              <p className="py-4 text-center text-sm text-muted-foreground">
                No other suites available.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={pending}>
              Cancel
            </Button>
            <Button onClick={attach} disabled={pending || picked.size === 0}>
              {pending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Add {picked.size || ""}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
