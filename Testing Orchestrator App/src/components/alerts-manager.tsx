"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Loader2, Save } from "lucide-react";
import type { AlertConfig, AlertRecord } from "@/lib/alerts";
import { updateAlertConfig } from "@/app/alerts/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const TOKENS = ["FAIL", "ERROR", "WARN", "P1", "P2"];

export function AlertsManager({
  config,
  alerts,
  suites,
}: {
  config: AlertConfig;
  alerts: AlertRecord[];
  suites: string[];
}) {
  const [cfg, setCfg] = useState<AlertConfig>(config);
  const [pending, startTransition] = useTransition();

  function toggleToken(t: string) {
    setCfg((c) => ({
      ...c,
      on: c.on.includes(t) ? c.on.filter((x) => x !== t) : [...c.on, t],
    }));
  }

  function toggleSuite(s: string) {
    setCfg((c) => {
      const cur = c.suites ?? [];
      const next = cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s];
      return { ...c, suites: next.length ? next : null };
    });
  }

  function save() {
    startTransition(async () => {
      try {
        await updateAlertConfig(cfg);
        toast.success("Saved alert settings");
      } catch (e) {
        toast.error(String(e));
      }
    });
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Alert rules</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={cfg.enabled}
              onCheckedChange={(v) => setCfg({ ...cfg, enabled: Boolean(v) })}
            />
            <span className="font-medium">Enable alerting</span>
          </label>

          <div>
            <Label>Trigger on (status or severity)</Label>
            <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1.5">
              {TOKENS.map((t) => (
                <label key={t} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={cfg.on.includes(t)} onCheckedChange={() => toggleToken(t)} />
                  {t}
                </label>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label>Webhook env var (Power Automate URL)</Label>
              <Input
                value={cfg.webhookEnv}
                onChange={(e) => setCfg({ ...cfg, webhookEnv: e.target.value })}
                className="mt-1 font-mono text-xs"
                placeholder="TEAMS_WEBHOOK_URL"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                The URL itself lives in <code>.env</code> — never stored here.
              </p>
            </div>
            <div>
              <Label>Channel</Label>
              <Input
                value={cfg.channel ?? "teams"}
                onChange={(e) => setCfg({ ...cfg, channel: e.target.value })}
                className="mt-1"
              />
            </div>
          </div>

          {suites.length > 0 && (
            <div>
              <Label>Limit to suites (none = all)</Label>
              <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
                {suites.map((s) => (
                  <label key={s} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={(cfg.suites ?? []).includes(s)}
                      onCheckedChange={() => toggleSuite(s)}
                    />
                    <span className="truncate font-mono text-xs">{s}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <Button size="sm" onClick={save} disabled={pending}>
            {pending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}
            Save settings
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Recent alerts <span className="font-normal text-muted-foreground">({alerts.length})</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Suite / Run</TableHead>
                  <TableHead>Member</TableHead>
                  <TableHead>Severity</TableHead>
                  <TableHead>Failures</TableHead>
                  <TableHead>Delivery</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {alerts.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {new Date(a.ts).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <div className="text-sm font-medium">{a.suite ?? "—"}</div>
                      <a href={`/runs/${a.run_ref}`} className="font-mono text-xs text-primary hover:underline">
                        {a.run_id}
                      </a>
                    </TableCell>
                    <TableCell className="text-sm">{a.member}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{a.worst_severity ?? "—"}</Badge>
                    </TableCell>
                    <TableCell className="text-sm">
                      {a.failed} fail · {a.errored} error
                    </TableCell>
                    <TableCell className="text-xs">
                      {!a.webhook_configured ? (
                        <span className="text-muted-foreground">no webhook</span>
                      ) : a.sent ? (
                        <span className="text-status-pass">sent</span>
                      ) : (
                        <span className="text-status-fail">{a.send_error ?? "failed"}</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {alerts.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-10 text-center text-sm text-muted-foreground">
                      No alerts yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
