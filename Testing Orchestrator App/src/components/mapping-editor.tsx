"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Loader2, Save } from "lucide-react";
import type {
  MappingBook,
  BusinessRule,
} from "@/lib/configStore";
import { saveMappingBook } from "@/app/mappings/actions";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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

const BLANK_RULE: BusinessRule = {
  rule_id: "",
  target_table: "",
  rule_type: "value_equals",
  params: {},
  severity: "P3",
  description: "",
  active: true,
};

export function MappingEditor({ name, book: initial }: { name: string; book: MappingBook }) {
  const [book, setBook] = useState<MappingBook>(initial);
  const [dirty, setDirty] = useState(false);
  const [pending, startTransition] = useTransition();

  // rule JSON editor
  const [editIdx, setEditIdx] = useState<number | null>(null);
  const [ruleText, setRuleText] = useState("");

  function mutate(next: MappingBook) {
    setBook(next);
    setDirty(true);
  }

  function toggleRule(i: number) {
    const rules = book.business_rules.map((r, idx) =>
      idx === i ? { ...r, active: !(r.active ?? true) } : r,
    );
    mutate({ ...book, business_rules: rules });
  }

  function deleteRule(i: number) {
    if (!confirm("Delete this rule?")) return;
    mutate({ ...book, business_rules: book.business_rules.filter((_, idx) => idx !== i) });
  }

  function openRule(i: number) {
    setEditIdx(i);
    setRuleText(JSON.stringify(book.business_rules[i], null, 2));
  }

  function addRule() {
    const rules = [...book.business_rules, { ...BLANK_RULE }];
    mutate({ ...book, business_rules: rules });
    setEditIdx(rules.length - 1);
    setRuleText(JSON.stringify(BLANK_RULE, null, 2));
  }

  function saveRule() {
    if (editIdx === null) return;
    let parsed: BusinessRule;
    try {
      parsed = JSON.parse(ruleText);
    } catch {
      return toast.error("Rule must be valid JSON");
    }
    if (!parsed.rule_id || !parsed.target_table || !parsed.rule_type) {
      return toast.error("rule_id, target_table and rule_type are required");
    }
    const rules = book.business_rules.map((r, idx) => (idx === editIdx ? parsed : r));
    mutate({ ...book, business_rules: rules });
    setEditIdx(null);
  }

  function toggleRef(i: number) {
    const ref = book.ref_integrity.map((r, idx) =>
      idx === i ? { ...r, active: !(r.active ?? true) } : r,
    );
    mutate({ ...book, ref_integrity: ref });
  }

  function save() {
    startTransition(async () => {
      try {
        await saveMappingBook(name, book);
        setDirty(false);
        toast.success("Mapping saved");
      } catch (e) {
        toast.error(String(e));
      }
    });
  }

  return (
    <div className="space-y-4">
      {dirty && (
        <div className="sticky top-0 z-10 flex items-center justify-between rounded-lg border bg-primary/5 px-4 py-2 text-sm">
          <span className="text-muted-foreground">You have unsaved changes.</span>
          <Button size="sm" onClick={save} disabled={pending}>
            {pending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}
            Save
          </Button>
        </div>
      )}

      <Tabs defaultValue="rules">
        <TabsList>
          <TabsTrigger value="tables">Tables ({book.tables.length})</TabsTrigger>
          <TabsTrigger value="rules">Business rules ({book.business_rules.length})</TabsTrigger>
          <TabsTrigger value="ref">Referential integrity ({book.ref_integrity.length})</TabsTrigger>
        </TabsList>

        {/* Tables */}
        <TabsContent value="tables" className="space-y-3">
          {book.tables.map((t) => (
            <Card key={t.target_table}>
              <CardHeader className="pb-2">
                <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                  {t.target_table}
                  {t.layer && <Badge variant="secondary">{t.layer}</Badge>}
                  <Badge variant="outline">{t.load_type ?? "full"}</Badge>
                  {t.active === false && <Badge variant="outline">inactive</Badge>}
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  source: {t.source_object ?? "—"} · keys: {(t.key_columns ?? []).join(", ") || "—"}
                </p>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Target column</TableHead>
                        <TableHead>Source column</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Nullable</TableHead>
                        <TableHead>Compare</TableHead>
                        <TableHead>Transformation</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(t.columns ?? []).map((c) => (
                        <TableRow key={c.target_column}>
                          <TableCell className="font-medium">
                            {c.target_column}
                            {c.is_key && <Badge variant="outline" className="ml-1.5">key</Badge>}
                          </TableCell>
                          <TableCell className="text-muted-foreground">{c.source_column ?? "—"}</TableCell>
                          <TableCell className="text-xs">{c.target_datatype ?? "—"}</TableCell>
                          <TableCell className="text-xs">{c.nullable === false ? "no" : "yes"}</TableCell>
                          <TableCell className="text-xs">{c.compare === false ? "no" : "yes"}</TableCell>
                          <TableCell className="max-w-[16rem] truncate text-xs text-muted-foreground">
                            {c.transformation ?? ""}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        {/* Business rules */}
        <TabsContent value="rules" className="space-y-3">
          <div className="flex justify-end">
            <Button size="sm" onClick={addRule}>
              <Plus className="mr-1.5 h-4 w-4" /> Add rule
            </Button>
          </div>
          <div className="overflow-hidden rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-16">Active</TableHead>
                  <TableHead>Rule</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Sev</TableHead>
                  <TableHead className="w-20 text-right">Edit</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {book.business_rules.map((r, i) => (
                  <TableRow key={`${r.rule_id}-${i}`} className={r.active === false ? "opacity-50" : ""}>
                    <TableCell>
                      <Checkbox checked={r.active ?? true} onCheckedChange={() => toggleRule(i)} />
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">{r.rule_id || "(new)"}</div>
                      <div className="text-xs text-muted-foreground">{r.description}</div>
                    </TableCell>
                    <TableCell className="text-sm">{r.target_table}</TableCell>
                    <TableCell className="font-mono text-xs">{r.rule_type}</TableCell>
                    <TableCell className="text-xs font-bold">{r.severity ?? "P3"}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => openRule(i)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => deleteRule(i)}>
                          <Trash2 className="h-4 w-4 text-status-fail" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {book.business_rules.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                      No business rules.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        {/* Ref integrity */}
        <TabsContent value="ref" className="space-y-3">
          <div className="overflow-hidden rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-16">Active</TableHead>
                  <TableHead>Child</TableHead>
                  <TableHead>Parent</TableHead>
                  <TableHead>Sev</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {book.ref_integrity.map((r, i) => (
                  <TableRow key={i} className={r.active === false ? "opacity-50" : ""}>
                    <TableCell>
                      <Checkbox checked={r.active ?? true} onCheckedChange={() => toggleRef(i)} />
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {r.child_table}.[{(r.child_columns ?? []).join(", ")}]
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {r.parent_table}.[{(r.parent_columns ?? []).join(", ")}]
                    </TableCell>
                    <TableCell className="text-xs font-bold">{r.severity ?? "P2"}</TableCell>
                  </TableRow>
                ))}
                {book.ref_integrity.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                      No referential-integrity rules.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>

      <Sheet open={editIdx !== null} onOpenChange={(o) => !o && setEditIdx(null)}>
        <SheetContent className="overflow-y-auto sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>Edit rule</SheetTitle>
            <SheetDescription>
              Edit the rule as JSON. rule_type values: value_equals, allowed_values, conditional,
              must_exist, must_not_exist, combine, split, not_null, range, unique, valid_expr.
            </SheetDescription>
          </SheetHeader>
          <div className="py-4">
            <Textarea
              value={ruleText}
              onChange={(e) => setRuleText(e.target.value)}
              className="min-h-[22rem] font-mono text-xs"
            />
          </div>
          <SheetFooter>
            <Button variant="outline" onClick={() => setEditIdx(null)}>
              Cancel
            </Button>
            <Button onClick={saveRule}>Apply</Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
  );
}
