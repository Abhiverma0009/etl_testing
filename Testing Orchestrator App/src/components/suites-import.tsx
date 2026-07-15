"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2, Upload, FileSpreadsheet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { importSuites } from "@/app/suites/actions";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

// TestCases columns, kept readable for a non-developer QA lead.
const TESTCASE_COLS: { col: string; req: boolean; desc: string }[] = [
  { col: "name", req: true, desc: "Unique test-case name → becomes the suite file." },
  { col: "scenario", req: false, desc: "Scenario id or name to group under (auto-created if new)." },
  { col: "source", req: false, desc: "Source connection name (blank = none)." },
  { col: "target", req: true, desc: "Target connection name (must already exist)." },
  { col: "mapping", req: false, desc: "Mapping name (must already exist under Mappings)." },
  { col: "tests", req: false, desc: "Comma-separated test categories (blank = run all)." },
  { col: "reports", req: false, desc: "Comma-separated report ids (for GVC/MD&A report cases)." },
  { col: "options", req: false, desc: 'JSON object, e.g. {"variance_threshold": 0.0001}.' },
  { col: "tables", req: false, desc: "Table name(s) to scope to — comma-separated, or JSON for per-table options." },
  { col: "expected", req: false, desc: 'Blank/pass (normal) or "fail" for a negative test case — passes only when it detects a failure.' },
];

const SCENARIO_COLS: { col: string; req: boolean; desc: string }[] = [
  { col: "id", req: true, desc: "Scenario id (short key, e.g. nightly_regression)." },
  { col: "name", req: false, desc: "Display name." },
  { col: "description", req: false, desc: "Free text." },
];

export function SuitesImport() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await importSuites(fd);
      if (res.ok) {
        toast.success(res.message);
        if (res.warnings?.length) {
          toast.warning(`${res.warnings.length} warning(s): ${res.warnings.slice(0, 3).join(" · ")}`, {
            duration: 9000,
          });
        }
        router.refresh();
      } else {
        toast.error(res.message, { duration: 9000 });
      }
    } catch (err) {
      toast.error("Import failed: " + String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <FormatHelp />
      <input ref={inputRef} type="file" accept=".xlsx,.xlsm" hidden onChange={onFile} />
      <Button variant="outline" onClick={() => inputRef.current?.click()} disabled={busy}>
        {busy ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <Upload className="mr-2 h-4 w-4" />
        )}
        Import test cases (.xlsx)
      </Button>
    </div>
  );
}

function ColTable({ rows }: { rows: { col: string; req: boolean; desc: string }[] }) {
  return (
    <div className="overflow-hidden rounded-md border">
      <table className="w-full text-sm">
        <tbody>
          {rows.map((r) => (
            <tr key={r.col} className="border-b last:border-b-0">
              <td className="whitespace-nowrap px-3 py-1.5 align-top font-mono text-xs">
                {r.col}
                {r.req && <span className="ml-1 text-status-fail">*</span>}
              </td>
              <td className="px-3 py-1.5 align-top text-muted-foreground">{r.desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FormatHelp() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost">
          <FileSpreadsheet className="mr-2 h-4 w-4" />
          Format
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Test-case workbook format</DialogTitle>
          <DialogDescription>
            An Excel workbook with a <b>TestCases</b> sheet (one row per test
            case) and an optional <b>Scenarios</b> sheet. Column names are
            case-insensitive. <span className="text-status-fail">*</span> = required.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 text-sm">
          <div>
            <div className="mb-1.5 font-semibold">Sheet: TestCases</div>
            <ColTable rows={TESTCASE_COLS} />
          </div>
          <div>
            <div className="mb-1.5 font-semibold">Sheet: Scenarios (optional)</div>
            <ColTable rows={SCENARIO_COLS} />
          </div>
          <p className="text-xs text-muted-foreground">
            Connections and mappings are referenced by name and must already
            exist (add them under Connections / Mappings first). Unknown
            references import with a warning so you can fix them later.
          </p>
          <div className="rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
            <div className="mb-1 font-medium text-foreground">Test cases that aren&rsquo;t source→target</div>
            Leave <code className="rounded bg-muted px-1 py-0.5">source</code> blank and pick only
            target-side categories in <code className="rounded bg-muted px-1 py-0.5">tests</code> —
            e.g. <code className="rounded bg-muted px-1 py-0.5">schema</code>,{" "}
            <code className="rounded bg-muted px-1 py-0.5">datatype</code> (column format),{" "}
            <code className="rounded bg-muted px-1 py-0.5">completeness</code>,{" "}
            <code className="rounded bg-muted px-1 py-0.5">null_handling</code>,{" "}
            <code className="rounded bg-muted px-1 py-0.5">business_rules</code>. Comparison
            categories (reconciliation, transformation, row_count) simply skip when there&rsquo;s no
            source. A data test case still needs a <code className="rounded bg-muted px-1 py-0.5">mapping</code>{" "}
            (it defines the target table&rsquo;s expected columns/formats/rules); only a{" "}
            <code className="rounded bg-muted px-1 py-0.5">reports</code>-based row needs no mapping.
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
