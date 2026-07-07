"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Play, Loader2, Plus, Pencil, Trash2, Save } from "lucide-react";
import type { ReportBook, ReportTab, ReportMeasure } from "@/lib/reportsStore";
import { saveReportBook, removeReportBook } from "@/app/reports/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

function emptyTab(): ReportTab {
  return {
    name: "",
    key_columns: [],
    compare_columns: [],
    measures: [],
    actual: {},
    expected: {},
  };
}

export function ReportEditor({
  report,
  connections,
  member,
}: {
  report: ReportBook;
  connections: string[];
  member: string;
}) {
  const router = useRouter();
  const [book, setBook] = useState<ReportBook>(report);
  const [pending, startTransition] = useTransition();

  // tab editing
  const [open, setOpen] = useState(false);
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [draft, setDraft] = useState<ReportTab | null>(null);
  const [keyText, setKeyText] = useState("");
  const [cmpText, setCmpText] = useState("");

  // run state
  const [running, setRunning] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  function persist(next: ReportBook) {
    setBook(next);
    startTransition(async () => {
      try {
        await saveReportBook(next);
      } catch (e) {
        toast.error(String(e));
      }
    });
  }

  function saveMeta() {
    persist(book);
    toast.success("Saved report");
  }

  function openTab(index: number | null) {
    setEditIndex(index);
    const t = index === null ? emptyTab() : structuredClone(book.tabs[index]);
    setDraft(t);
    setKeyText((t.key_columns ?? []).join(", "));
    setCmpText((t.compare_columns ?? []).join(", "));
    setOpen(true);
  }

  function saveTab() {
    if (!draft) return;
    if (!draft.name.trim()) return toast.error("Tab name is required");
    const t: ReportTab = {
      ...draft,
      name: draft.name.trim(),
      key_columns: csv(keyText),
      compare_columns: csv(cmpText),
      measures: (draft.measures ?? []).filter((m) => m.column?.trim()),
    };
    const tabs = [...book.tabs];
    if (editIndex === null) tabs.push(t);
    else tabs[editIndex] = t;
    persist({ ...book, tabs });
    setOpen(false);
    toast.success(editIndex === null ? "Added tab" : "Updated tab");
  }

  function deleteTab(index: number) {
    if (!confirm(`Delete tab '${book.tabs[index].name}'?`)) return;
    persist({ ...book, tabs: book.tabs.filter((_, i) => i !== index) });
  }

  function delReport() {
    if (!confirm(`Delete report '${book.name}'? This removes its file.`)) return;
    startTransition(async () => {
      await removeReportBook(book.id);
      toast.success("Deleted report");
      router.push("/reports");
    });
  }

  async function run() {
    if (book.tabs.length === 0) return toast.error("Add at least one tab first");
    setRunning(true);
    let res: Response;
    try {
      res = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reportId: book.id }),
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
    const es = new EventSource(`/api/runs/${data.jobId}/stream`);
    esRef.current = es;
    let runId: string | null = null;
    es.onmessage = (e) => {
      let ev: Record<string, unknown>;
      try {
        ev = JSON.parse(e.data);
      } catch {
        return;
      }
      if (ev.event === "run_start") runId = (ev.run_id as string) ?? null;
      if (ev.event === "job_end") {
        es.close();
        setRunning(false);
        const rid = (ev.run_id as string) ?? runId;
        if (ev.error) toast.error("Run failed: " + String(ev.error));
        else if (ev.exit_code === 0) toast.success("Report matches — all tabs passed.");
        else toast.warning("Report run finished — some tabs failed.");
        if (rid) setTimeout(() => router.push(`/runs/${member}~${rid}`), 800);
      }
    };
    es.onerror = () => {};
  }

  // measure row helpers (draft)
  function setMeasure(i: number, patch: Partial<ReportMeasure>) {
    if (!draft) return;
    const measures = [...(draft.measures ?? [])];
    measures[i] = { ...measures[i], ...patch };
    setDraft({ ...draft, measures });
  }
  function addMeasure() {
    if (!draft) return;
    setDraft({ ...draft, measures: [...(draft.measures ?? []), { column: "", tolerance: 0.0001 }] });
  }
  function delMeasure(i: number) {
    if (!draft) return;
    setDraft({ ...draft, measures: (draft.measures ?? []).filter((_, j) => j !== i) });
  }

  function connSelect(value: string | undefined, onChange: (v: string) => void) {
    return (
      <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? "" : v)}>
        <SelectTrigger className="mt-1">
          <SelectValue placeholder="Select…" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>(use report default)</SelectItem>
          {connections.map((c) => (
            <SelectItem key={c} value={c}>
              {c}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  return (
    <div className="space-y-5">
      {/* Meta + actions */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Report settings</CardTitle>
          <div className="flex gap-2">
            <Button size="sm" onClick={run} disabled={running || pending}>
              {running ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-1.5 h-4 w-4" />
              )}
              {running ? "Running…" : "Run report"}
            </Button>
            <Button size="sm" variant="outline" onClick={delReport} disabled={pending}>
              <Trash2 className="mr-1.5 h-4 w-4 text-status-fail" />
              Delete
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label>Name</Label>
              <Input
                value={book.name}
                onChange={(e) => setBook({ ...book, name: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Type</Label>
              <Select value={book.type || "GVC"} onValueChange={(v) => setBook({ ...book, type: v })}>
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["GVC", "MDA", "SIS", "DQ", "OTHER"].map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Default ACTUAL connection (Snowflake)</Label>
              {connSelect(book.actual_connection, (v) =>
                setBook({ ...book, actual_connection: v || undefined }),
              )}
            </div>
            <div>
              <Label>Default EXPECTED connection (Access)</Label>
              {connSelect(book.expected_connection, (v) =>
                setBook({ ...book, expected_connection: v || undefined }),
              )}
            </div>
          </div>
          <Button size="sm" variant="secondary" onClick={saveMeta} disabled={pending}>
            <Save className="mr-1.5 h-4 w-4" />
            Save settings
          </Button>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">
            Tabs <span className="font-normal text-muted-foreground">({book.tabs.length})</span>
          </CardTitle>
          <Button size="sm" onClick={() => openTab(null)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add tab
          </Button>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tab</TableHead>
                  <TableHead>Key columns</TableHead>
                  <TableHead>Compare</TableHead>
                  <TableHead>Measures</TableHead>
                  <TableHead className="w-20 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {book.tabs.map((t, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-medium">{t.name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {(t.key_columns ?? []).join(", ") || "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {(t.compare_columns ?? []).join(", ") || "(auto)"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {(t.measures ?? []).length}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => openTab(i)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => deleteTab(i)}>
                          <Trash2 className="h-4 w-4 text-status-fail" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {book.tabs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-10 text-center text-sm text-muted-foreground">
                      No tabs yet. Add one to define a query pair.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Tab editor */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="overflow-y-auto sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>{editIndex === null ? "New tab" : "Edit tab"}</SheetTitle>
            <SheetDescription>
              ACTUAL = new Snowflake query · EXPECTED = legacy Access query. Both must
              return the same columns (keys + compared values).
            </SheetDescription>
          </SheetHeader>
          {draft && (
            <div className="space-y-4 py-4">
              <div>
                <Label>Tab name</Label>
                <Input
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  placeholder="Q01 - Fund Performance"
                  className="mt-1"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Key columns (comma-sep)</Label>
                  <Input
                    value={keyText}
                    onChange={(e) => setKeyText(e.target.value)}
                    placeholder="FUND_CODE, PERIOD"
                    className="mt-1 font-mono text-xs"
                  />
                </div>
                <div>
                  <Label>Compare columns (blank = auto)</Label>
                  <Input
                    value={cmpText}
                    onChange={(e) => setCmpText(e.target.value)}
                    placeholder="NAV, IRR"
                    className="mt-1 font-mono text-xs"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>ACTUAL connection</Label>
                  {connSelect(draft.actual.connection, (v) =>
                    setDraft({ ...draft, actual: { ...draft.actual, connection: v || undefined } }),
                  )}
                </div>
                <div>
                  <Label>EXPECTED connection</Label>
                  {connSelect(draft.expected.connection, (v) =>
                    setDraft({ ...draft, expected: { ...draft.expected, connection: v || undefined } }),
                  )}
                </div>
              </div>
              <div>
                <Label>ACTUAL query (Snowflake)</Label>
                <Textarea
                  value={draft.actual.query ?? ""}
                  onChange={(e) => setDraft({ ...draft, actual: { ...draft.actual, query: e.target.value } })}
                  rows={5}
                  placeholder="SELECT FUND_CODE, PERIOD, NAV, IRR FROM GOLD..."
                  className="mt-1 font-mono text-xs"
                />
              </div>
              <div>
                <Label>EXPECTED query (legacy Access)</Label>
                <Textarea
                  value={draft.expected.query ?? ""}
                  onChange={(e) => setDraft({ ...draft, expected: { ...draft.expected, query: e.target.value } })}
                  rows={5}
                  placeholder="SELECT FUND_CODE, PERIOD, NAV, IRR FROM ..."
                  className="mt-1 font-mono text-xs"
                />
              </div>
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <Label>Measures (aggregate totals to reconcile)</Label>
                  <Button variant="ghost" size="sm" onClick={addMeasure}>
                    <Plus className="mr-1 h-3.5 w-3.5" />
                    Add
                  </Button>
                </div>
                <div className="space-y-2">
                  {(draft.measures ?? []).map((m, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Input
                        value={m.label ?? ""}
                        onChange={(e) => setMeasure(i, { label: e.target.value })}
                        placeholder="Total NAV"
                        className="text-xs"
                      />
                      <Input
                        value={m.column}
                        onChange={(e) => setMeasure(i, { column: e.target.value })}
                        placeholder="column"
                        className="font-mono text-xs"
                      />
                      <Input
                        value={String(m.tolerance ?? 0.0001)}
                        onChange={(e) => setMeasure(i, { tolerance: Number(e.target.value) })}
                        placeholder="tol"
                        className="w-24 font-mono text-xs"
                      />
                      <Button variant="ghost" size="sm" onClick={() => delMeasure(i)}>
                        <Trash2 className="h-4 w-4 text-status-fail" />
                      </Button>
                    </div>
                  ))}
                  {(draft.measures ?? []).length === 0 && (
                    <p className="text-xs text-muted-foreground">No measures (row-level check only).</p>
                  )}
                </div>
              </div>
            </div>
          )}
          <SheetFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={saveTab}>Save tab</Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
  );
}
