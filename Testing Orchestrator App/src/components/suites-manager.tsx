"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Loader2 } from "lucide-react";
import type { SuiteConfig } from "@/lib/types";
import { categoryLabel } from "@/lib/categories";
import { saveSuite, removeSuite } from "@/app/suites/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const NONE = "__none__";

interface Draft {
  name: string;
  source: string;
  target: string;
  mapping: string;
  scenario: string;
  tests: Set<string>;
  reports: Set<string>;
  optionsText: string;
  tablesText: string;
  isNew: boolean;
}

export function SuitesManager({
  suites,
  connections,
  mappings,
  categories,
  reports,
  scenarios,
}: {
  suites: SuiteConfig[];
  connections: string[];
  mappings: string[];
  categories: string[];
  reports: string[];
  scenarios: { id: string; name: string }[];
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [pending, startTransition] = useTransition();
  const searchParams = useSearchParams();
  const presetHandled = useRef(false);

  function openNew(presetScenario?: string) {
    setDraft({
      name: "",
      source: NONE,
      target: connections[0] ?? "",
      mapping: mappings[0] ?? "",
      scenario: presetScenario && scenarios.some((s) => s.id === presetScenario)
        ? presetScenario
        : NONE,
      tests: new Set(),
      reports: new Set(),
      optionsText: "{\n  \"variance_threshold\": 0.0001\n}",
      tablesText: "[]",
      isNew: true,
    });
    setOpen(true);
  }

  // Arriving from a scenario's "New test case" button (/suites?newScenario=<id>)
  // opens the new-suite editor pre-set to that scenario.
  useEffect(() => {
    if (presetHandled.current) return;
    const ns = searchParams.get("newScenario");
    if (ns && scenarios.some((s) => s.id === ns)) {
      presetHandled.current = true;
      openNew(ns);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  function openEdit(s: SuiteConfig) {
    setDraft({
      name: s.name,
      source: s.source ?? NONE,
      target: s.target ?? "",
      mapping: (s.mapping ?? "").replace(/^config\/mappings\//, "").replace(/\.json$/, ""),
      scenario: s.scenario ?? NONE,
      tests: new Set(s.tests ?? []),
      reports: new Set(s.reports ?? []),
      optionsText: JSON.stringify(s.options ?? {}, null, 2),
      tablesText: JSON.stringify(s.tables ?? [], null, 2),
      isNew: false,
    });
    setOpen(true);
  }

  function toggleTest(c: string) {
    setDraft((d) => {
      if (!d) return d;
      const t = new Set(d.tests);
      if (t.has(c)) t.delete(c);
      else t.add(c);
      return { ...d, tests: t };
    });
  }

  function scenarioName(id?: string): string | null {
    if (!id) return null;
    return scenarios.find((sc) => sc.id === id)?.name ?? id;
  }

  function toggleReport(r: string) {
    setDraft((d) => {
      if (!d) return d;
      const t = new Set(d.reports);
      if (t.has(r)) t.delete(r);
      else t.add(r);
      return { ...d, reports: t };
    });
  }

  function save() {
    if (!draft) return;
    if (!draft.name.trim()) return toast.error("Name is required");
    if (!draft.target) return toast.error("Target is required");
    let options: Record<string, unknown>;
    let tables: unknown[];
    try {
      options = draft.optionsText.trim() ? JSON.parse(draft.optionsText) : {};
    } catch {
      return toast.error("Options must be valid JSON");
    }
    try {
      tables = draft.tablesText.trim() ? JSON.parse(draft.tablesText) : [];
    } catch {
      return toast.error("Tables must be valid JSON (an array)");
    }
    const reportsArr = Array.from(draft.reports);
    const suite: SuiteConfig = {
      name: draft.name.trim(),
      connections: "config/connections.yaml",
      mapping: draft.mapping ? `config/mappings/${draft.mapping}.json` : undefined,
      source: draft.source === NONE ? null : draft.source,
      target: draft.target,
      options,
      tests: Array.from(draft.tests),
      tables: tables as SuiteConfig["tables"],
      ...(reportsArr.length ? { reports: reportsArr } : {}),
      ...(draft.scenario !== NONE ? { scenario: draft.scenario } : {}),
    };
    startTransition(async () => {
      try {
        await saveSuite(suite);
        toast.success(`Saved suite '${suite.name}'`);
        setOpen(false);
      } catch (e) {
        toast.error(String(e));
      }
    });
  }

  function del(name: string) {
    if (!confirm(`Delete suite '${name}'?`)) return;
    startTransition(async () => {
      await removeSuite(name);
      toast.success(`Deleted '${name}'`);
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => openNew()}>
          <Plus className="mr-1.5 h-4 w-4" />
          Add suite
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Scenario</TableHead>
              <TableHead>Source → Target</TableHead>
              <TableHead>Mapping</TableHead>
              <TableHead>Tests</TableHead>
              <TableHead className="w-24 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {suites.map((s) => (
              <TableRow key={s.name}>
                <TableCell className="font-medium">{s.name}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {scenarioName(s.scenario) ?? "—"}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {(s.source ?? "—") + " → " + s.target}
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {(s.mapping ?? "").replace(/^config\/mappings\//, "")}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {s.tests?.length ? `${s.tests.length} categories` : "all"}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="sm" onClick={() => openEdit(s)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => del(s.name)}>
                      <Trash2 className="h-4 w-4 text-status-fail" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {suites.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="py-10 text-center text-sm text-muted-foreground">
                  No suites yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="overflow-y-auto sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>{draft?.isNew ? "New suite" : "Edit suite"}</SheetTitle>
            <SheetDescription>A validation hop: source → target with a mapping.</SheetDescription>
          </SheetHeader>

          {draft && (
            <div className="space-y-4 py-4">
              <div>
                <Label>Name</Label>
                <Input
                  value={draft.name}
                  disabled={!draft.isNew}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  placeholder="bronze_to_silver"
                  className="mt-1"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Source</Label>
                  <Select value={draft.source} onValueChange={(v) => setDraft({ ...draft, source: v })}>
                    <SelectTrigger className="mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>(none)</SelectItem>
                      {connections.map((c) => (
                        <SelectItem key={c} value={c}>
                          {c}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Target</Label>
                  <Select value={draft.target} onValueChange={(v) => setDraft({ ...draft, target: v })}>
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="Select…" />
                    </SelectTrigger>
                    <SelectContent>
                      {connections.map((c) => (
                        <SelectItem key={c} value={c}>
                          {c}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label>Mapping</Label>
                <Select value={draft.mapping} onValueChange={(v) => setDraft({ ...draft, mapping: v })}>
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Select…" />
                  </SelectTrigger>
                  <SelectContent>
                    {mappings.map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Test scenario</Label>
                <Select value={draft.scenario} onValueChange={(v) => setDraft({ ...draft, scenario: v })}>
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="(none)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>(none — ungrouped)</SelectItem>
                    {scenarios.map((sc) => (
                      <SelectItem key={sc.id} value={sc.id}>
                        {sc.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Tests</Label>
                <p className="mb-1.5 text-xs text-muted-foreground">
                  Leave all unchecked to run every category.
                </p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                  {categories.map((c) => (
                    <label key={c} className="flex items-center gap-2 text-sm">
                      <Checkbox checked={draft.tests.has(c)} onCheckedChange={() => toggleTest(c)} />
                      {categoryLabel(c)}
                    </label>
                  ))}
                </div>
              </div>
              {reports.length > 0 && (
                <div>
                  <Label>Reports</Label>
                  <p className="mb-1.5 text-xs text-muted-foreground">
                    Attach GVC / MD&A report tests; the <code>report</code> category
                    runs them automatically.
                  </p>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                    {reports.map((r) => (
                      <label key={r} className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={draft.reports.has(r)}
                          onCheckedChange={() => toggleReport(r)}
                        />
                        <span className="truncate font-mono text-xs">{r}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
              <div>
                <Label>Options (JSON)</Label>
                <Textarea
                  value={draft.optionsText}
                  onChange={(e) => setDraft({ ...draft, optionsText: e.target.value })}
                  className="mt-1 font-mono text-xs"
                  rows={5}
                />
              </div>
              <div>
                <Label>Per-table options (JSON array)</Label>
                <Textarea
                  value={draft.tablesText}
                  onChange={(e) => setDraft({ ...draft, tablesText: e.target.value })}
                  className="mt-1 font-mono text-xs"
                  rows={6}
                />
              </div>
            </div>
          )}

          <SheetFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={pending}>
              Cancel
            </Button>
            <Button onClick={save} disabled={pending}>
              {pending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Save
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
  );
}
