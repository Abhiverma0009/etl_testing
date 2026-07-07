"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, PlugZap, Loader2 } from "lucide-react";
import type { ConnectionConfig, ConnectionType } from "@/lib/types";
import { saveConnection, removeConnection, testConnection } from "@/app/connections/actions";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

type Field = { key: string; label: string; placeholder?: string; hint?: string };

const FIELDS: Record<ConnectionType, Field[]> = {
  snowflake: [
    { key: "account", label: "Account", placeholder: "org-account.region" },
    { key: "user", label: "User", hint: "literal or ${ENV_VAR}" },
    { key: "password", label: "Password", hint: "use ${ENV_VAR} — never a real secret" },
    { key: "role", label: "Role" },
    { key: "warehouse", label: "Warehouse" },
    { key: "database", label: "Database" },
    { key: "schema", label: "Schema" },
  ],
  access: [
    { key: "path", label: "Database path", placeholder: "C:\\data\\ValDB.accdb" },
    { key: "password", label: "Password", hint: "optional; use ${ENV_VAR}" },
  ],
  sqlserver: [
    { key: "host", label: "Host" },
    { key: "port", label: "Port", placeholder: "1433" },
    { key: "database", label: "Database" },
    { key: "user", label: "User", hint: "literal or ${ENV_VAR}" },
    { key: "password", label: "Password", hint: "use ${ENV_VAR}" },
    { key: "trusted", label: "Trusted (yes/no)", placeholder: "no" },
  ],
  files: [{ key: "base_dir", label: "Base directory", placeholder: "C:\\data\\feeds" }],
  sqlite: [{ key: "path", label: "Database path", placeholder: "samples/data/source.sqlite" }],
};

const TYPES: ConnectionType[] = ["snowflake", "access", "sqlserver", "files", "sqlite"];

function summary(c: ConnectionConfig): string {
  const f = FIELDS[c.type] ?? [];
  return f
    .filter((x) => x.key !== "password" && c[x.key])
    .map((x) => `${x.key}=${c[x.key]}`)
    .slice(0, 3)
    .join(" · ");
}

export function ConnectionsManager({ connections }: { connections: ConnectionConfig[] }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ConnectionConfig | null>(null);
  const [pending, startTransition] = useTransition();
  const [testing, setTesting] = useState<string | null>(null);

  function openNew() {
    setEditing({ name: "", type: "snowflake" });
    setOpen(true);
  }
  function openEdit(c: ConnectionConfig) {
    setEditing({ ...c });
    setOpen(true);
  }

  function setField(key: string, value: string) {
    setEditing((e) => (e ? { ...e, [key]: value } : e));
  }

  function save() {
    if (!editing) return;
    if (!editing.name.trim()) {
      toast.error("Name is required");
      return;
    }
    startTransition(async () => {
      try {
        await saveConnection(editing);
        toast.success(`Saved connection '${editing.name}'`);
        setOpen(false);
      } catch (e) {
        toast.error(String(e));
      }
    });
  }

  function del(name: string) {
    if (!confirm(`Delete connection '${name}'?`)) return;
    startTransition(async () => {
      await removeConnection(name);
      toast.success(`Deleted '${name}'`);
    });
  }

  async function test(name: string) {
    setTesting(name);
    try {
      const r = await testConnection(name);
      if (r.ok) toast.success(r.message);
      else toast.error(r.message);
    } finally {
      setTesting(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={openNew}>
          <Plus className="mr-1.5 h-4 w-4" />
          Add connection
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Details</TableHead>
              <TableHead className="w-40 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {connections.map((c) => (
              <TableRow key={c.name}>
                <TableCell className="font-medium">{c.name}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{c.type}</Badge>
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {summary(c)}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => test(c.name)}
                      disabled={testing === c.name}
                      title="Test connection"
                    >
                      {testing === c.name ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <PlugZap className="h-4 w-4" />
                      )}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => openEdit(c)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => del(c.name)}>
                      <Trash2 className="h-4 w-4 text-status-fail" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {connections.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="py-10 text-center text-sm text-muted-foreground">
                  No connections yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="overflow-y-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle>{editing?.name ? "Edit connection" : "New connection"}</SheetTitle>
            <SheetDescription>
              Secrets stay in <code>.env</code> — reference them here as{" "}
              <code>{"${VAR}"}</code>, never real values.
            </SheetDescription>
          </SheetHeader>

          {editing && (
            <div className="space-y-4 py-4">
              <div>
                <Label>Name</Label>
                <Input
                  value={editing.name}
                  onChange={(e) => setField("name", e.target.value)}
                  placeholder="snowflake_gold"
                  className="mt-1"
                />
              </div>
              <div>
                <Label>Type</Label>
                <Select
                  value={editing.type}
                  onValueChange={(v) => setEditing({ name: editing.name, type: v as ConnectionType })}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {FIELDS[editing.type].map((f) => (
                <div key={f.key}>
                  <Label>{f.label}</Label>
                  <Input
                    value={(editing[f.key] as string) ?? ""}
                    onChange={(e) => setField(f.key, e.target.value)}
                    placeholder={f.placeholder}
                    className="mt-1"
                  />
                  {f.hint && <p className="mt-1 text-xs text-muted-foreground">{f.hint}</p>}
                </div>
              ))}
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
