"use client";
 
import { useRef, useState, type ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2, Upload, FileSpreadsheet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { importMapping } from "@/app/mappings/actions";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
 
// Required + optional columns per sheet, kept in sync with config/mappings/README.md.
const SHEETS: { name: string; required: string; optional: string; purpose: string }[] = [
  {
    name: "Tables",
    required: "target_table",
    optional: "source_object, source_object_type, target_object_type, target_db, target_schema, layer, load_type, key_columns, active",
    purpose: "One row per target table/view.",
  },
  {
    name: "Columns",
    required: "target_table, target_column",
    optional: "source_column, source_datatype, target_datatype, nullable, transformation, default_value, compare, case_sensitive, numeric_tolerance",
    purpose: "One row per target column.",
  },
  {
    name: "BusinessRules",
    required: "rule_id, target_table, rule_type",
    optional: "column, expected, allowed_values, filter, params (JSON), severity, use_case, description, active",
    purpose: "One row per business rule (optional sheet).",
  },
  {
    name: "ReferentialIntegrity",
    required: "child_table, parent_table, child_columns, parent_columns",
    optional: "severity, description",
    purpose: "One row per foreign-key relationship (optional sheet).",
  },
];
 
export function MappingUpload() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
 
  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // let the user re-pick the same filename later
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await importMapping(fd);
      if (res.ok) {
        toast.success(res.message);
        router.refresh(); // new card shows immediately
      } else {
        toast.error(res.message, { duration: 8000 });
      }
    } catch (err) {
      toast.error("Upload failed: " + String(err));
    } finally {
      setBusy(false);
    }
  }
 
  return (
    <div className="flex items-center gap-2">
      <FormatHelp />
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xlsm"
        hidden
        onChange={onFile}
      />
      <Button onClick={() => inputRef.current?.click()} disabled={busy}>
        {busy ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <Upload className="mr-2 h-4 w-4" />
        )}
        Import mapping (.xlsx)
      </Button>
    </div>
  );
}
 
function FormatHelp() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline">
          <FileSpreadsheet className="mr-2 h-4 w-4" />
          Format
        </Button>
      </DialogTrigger>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Mapping workbook format</DialogTitle>
          <DialogDescription>
            An Excel workbook with the sheets below. Sheet and column names are
            case-insensitive and tolerant of spaces/underscores. The file&rsquo;s
            name becomes the mapping name in the app.
          </DialogDescription>
        </DialogHeader>
        <div className="-mr-2 min-h-0 flex-1 space-y-3 overflow-y-auto pr-2 text-sm">
          {SHEETS.map((s) => (
            <div key={s.name} className="rounded-md border p-3">
              <div className="font-semibold">{s.name}</div>
              <div className="mt-0.5 text-muted-foreground">{s.purpose}</div>
              <div className="mt-1.5">
                <span className="font-medium">Required:</span>{" "}
                <code className="rounded bg-muted px-1 py-0.5 text-xs">{s.required}</code>
              </div>
              <div className="mt-1">
                <span className="font-medium">Optional:</span>{" "}
                <span className="text-xs text-muted-foreground">{s.optional}</span>
              </div>
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            <span className="font-medium">Business rules</span> use{" "}
            <code className="rounded bg-muted px-1 py-0.5">rule_type</code> (e.g.{" "}
            <code className="rounded bg-muted px-1 py-0.5">valid_expr</code>,{" "}
            <code className="rounded bg-muted px-1 py-0.5">not_null</code>,{" "}
            <code className="rounded bg-muted px-1 py-0.5">allowed_values</code>,{" "}
            <code className="rounded bg-muted px-1 py-0.5">range</code>). Expressions
            that don&rsquo;t fit a column go in the{" "}
            <code className="rounded bg-muted px-1 py-0.5">params</code> JSON cell, e.g.{" "}
            <code className="rounded bg-muted px-1 py-0.5">{`{"valid_expr": "AMOUNT > 0"}`}</code>.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}