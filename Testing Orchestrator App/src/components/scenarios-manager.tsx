"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Loader2, Play, ChevronRight } from "lucide-react";
import { saveScenario, removeScenario } from "@/app/scenarios/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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

export interface ScenarioRow {
  id: string;
  name: string;
  description?: string;
  caseCount: number;
}

export function ScenariosManager({ scenarios }: { scenarios: ScenarioRow[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const [draft, setDraft] = useState<{ id: string; name: string; description: string; isNew: boolean } | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);

  function openNew() {
    setDraft({ id: "", name: "", description: "", isNew: true });
    setOpen(true);
  }
  function openEdit(s: ScenarioRow) {
    setDraft({ id: s.id, name: s.name, description: s.description ?? "", isNew: false });
    setOpen(true);
  }

  function save() {
    if (!draft) return;
    const id = draft.isNew
      ? draft.id.trim().replace(/[^a-zA-Z0-9_-]/g, "_")
      : draft.id;
    if (draft.isNew && !id) return toast.error("Id is required");
    if (!draft.name.trim()) return toast.error("Name is required");
    if (draft.isNew && scenarios.some((s) => s.id === id))
      return toast.error(`Scenario '${id}' already exists`);
    startTransition(async () => {
      try {
        await saveScenario({ id, name: draft.name.trim(), description: draft.description.trim() || undefined });
        toast.success(`Saved scenario '${draft.name.trim()}'`);
        setOpen(false);
      } catch (e) {
        toast.error(String(e));
      }
    });
  }

  function del(s: ScenarioRow) {
    if (!confirm(`Delete scenario '${s.name}'? Its ${s.caseCount} test case(s) become Ungrouped (suites are not deleted).`))
      return;
    startTransition(async () => {
      await removeScenario(s.id);
      toast.success(`Deleted '${s.name}'`);
    });
  }

  async function run(s: ScenarioRow) {
    if (s.caseCount === 0) return toast.error("This scenario has no test cases yet.");
    setRunningId(s.id);
    try {
      const res = await fetch(`/api/scenarios/${encodeURIComponent(s.id)}/run`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(data.error || `Failed to start (HTTP ${res.status})`);
        return;
      }
      toast.success(`Running scenario '${s.name}' — opening…`);
      router.push(`/scenarios/${s.id}`);
    } catch (e) {
      toast.error("Failed to start: " + String(e));
    } finally {
      setRunningId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={openNew}>
          <Plus className="mr-1.5 h-4 w-4" />
          Add scenario
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Scenario</TableHead>
              <TableHead>Description</TableHead>
              <TableHead className="w-28">Test cases</TableHead>
              <TableHead className="w-40 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {scenarios.map((s) => (
              <TableRow key={s.id}>
                <TableCell className="font-medium">
                  <Link href={`/scenarios/${s.id}`} className="inline-flex items-center gap-1 hover:text-primary">
                    {s.name}
                    <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                  </Link>
                </TableCell>
                <TableCell className="max-w-md truncate text-sm text-muted-foreground">
                  {s.description || "—"}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{s.caseCount}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button variant="outline" size="sm" onClick={() => run(s)} disabled={pending || s.caseCount === 0}>
                      {runningId === s.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Play className="h-4 w-4" />
                      )}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => openEdit(s)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => del(s)}>
                      <Trash2 className="h-4 w-4 text-status-fail" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {scenarios.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="py-10 text-center text-sm text-muted-foreground">
                  No scenarios yet. Add one, then assign suites to it from the Suites page.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{draft?.isNew ? "New scenario" : "Edit scenario"}</DialogTitle>
            <DialogDescription>
              A test scenario groups multiple test cases (suites). Assign suites to it
              from the Suites page.
            </DialogDescription>
          </DialogHeader>
          {draft && (
            <div className="space-y-4 py-2">
              <div>
                <Label>Id</Label>
                <Input
                  value={draft.id}
                  disabled={!draft.isNew}
                  onChange={(e) => setDraft({ ...draft, id: e.target.value })}
                  placeholder="gvc_migration"
                  className="mt-1 font-mono"
                />
              </div>
              <div>
                <Label>Name</Label>
                <Input
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  placeholder="GVC Report Migration"
                  className="mt-1"
                />
              </div>
              <div>
                <Label>Description</Label>
                <Textarea
                  value={draft.description}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  rows={3}
                  className="mt-1"
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={pending}>
              Cancel
            </Button>
            <Button onClick={save} disabled={pending}>
              {pending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
