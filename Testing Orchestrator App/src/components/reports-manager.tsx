"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Plus, ChevronRight, Loader2 } from "lucide-react";
import { saveReportBook } from "@/app/reports/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ReportRow {
  id: string;
  name: string;
  type: string;
  tabs: number;
  actual_connection: string;
  expected_connection: string;
}

const NONE = "__none__";

export function ReportsManager({
  reports,
  connections,
}: {
  reports: ReportRow[];
  connections: string[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("GVC");
  const [actual, setActual] = useState(NONE);
  const [expected, setExpected] = useState(NONE);

  function create() {
    const cleanId = id.trim().replace(/[^a-zA-Z0-9_-]/g, "_");
    if (!cleanId) return toast.error("A report id is required");
    if (!name.trim()) return toast.error("A report name is required");
    if (reports.some((r) => r.id === cleanId))
      return toast.error(`Report '${cleanId}' already exists`);
    startTransition(async () => {
      try {
        await saveReportBook({
          id: cleanId,
          name: name.trim(),
          type,
          actual_connection: actual === NONE ? undefined : actual,
          expected_connection: expected === NONE ? undefined : expected,
          tabs: [],
        });
        toast.success(`Created report '${name.trim()}'`);
        setOpen(false);
        router.push(`/reports/${cleanId}`);
      } catch (e) {
        toast.error(String(e));
      }
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" />
          Add report
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {reports.map((r) => (
          <Link key={r.id} href={`/reports/${r.id}`}>
            <Card className="transition-colors hover:border-primary">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-base">
                  <span className="truncate">{r.name}</span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm text-muted-foreground">
                <div>
                  {r.type ? (
                    <span className="mr-2 rounded bg-muted px-1.5 py-0.5 text-xs font-medium text-foreground">
                      {r.type}
                    </span>
                  ) : null}
                  {r.tabs} tab{r.tabs === 1 ? "" : "s"}
                </div>
                <div className="font-mono text-xs">
                  {(r.actual_connection || "?") + " ⇐ " + (r.expected_connection || "?")}
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
        {reports.length === 0 && (
          <div className="col-span-full rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
            No reports yet. Add one to define GVC / MD&A tab tests.
          </div>
        )}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New report</DialogTitle>
            <DialogDescription>
              A report (GVC, MD&A, …) holds tabs; each tab compares a new Snowflake
              query against the legacy Access query.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Id</Label>
                <Input
                  value={id}
                  onChange={(e) => setId(e.target.value)}
                  placeholder="gvc_q4_2025"
                  className="mt-1 font-mono"
                />
              </div>
              <div>
                <Label>Type</Label>
                <Select value={type} onValueChange={setType}>
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
            </div>
            <div>
              <Label>Name</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="GVC Reporting WB"
                className="mt-1"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>ACTUAL connection (new / Snowflake)</Label>
                <Select value={actual} onValueChange={setActual}>
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Select…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>(set per tab)</SelectItem>
                    {connections.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>EXPECTED connection (legacy / Access)</Label>
                <Select value={expected} onValueChange={setExpected}>
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Select…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>(set per tab)</SelectItem>
                    {connections.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={pending}>
              Cancel
            </Button>
            <Button onClick={create} disabled={pending}>
              {pending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
