import Link from "next/link";
import { notFound } from "next/navigation";
import { getScenario, suitesInScenario, listScenarios } from "@/lib/scenariosStore";
import { listSuites } from "@/lib/configStore";
import { getManifest } from "@/lib/runsStore";
import { listScenarioRunsFor } from "@/lib/scenarioRunsStore";
import { PageHeader } from "@/components/page-header";
import { ScenarioRunLauncher } from "@/components/scenario-run-launcher";
import { ScenarioCasesManager } from "@/components/scenario-cases-manager";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fmtDateTime } from "@/lib/format";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-dynamic";

const stem = (s?: string | null) => (s ?? "").replace(/\.ya?ml$/, "");

export default async function ScenarioDetailPage({ params }: { params: { id: string } }) {
  const scenario = await getScenario(params.id);
  if (!scenario) notFound();

  const [suites, allSuites, allScenarios, manifest, scenarioRuns] = await Promise.all([
    suitesInScenario(params.id),
    listSuites(),
    listScenarios(),
    getManifest(),
    listScenarioRunsFor(params.id),
  ]);

  // latest run per suite (manifest is newest-first)
  const latestBySuite = new Map<string, (typeof manifest.runs)[number]>();
  for (const r of manifest.runs) {
    const key = stem(r.suite);
    if (key && !latestBySuite.has(key)) latestBySuite.set(key, r);
  }

  const scenarioNameById = new Map(allScenarios.map((s) => [s.id, s.name]));
  // suites eligible to be added here = everything not already in this scenario
  const available = allSuites
    .filter((s) => s.scenario !== params.id)
    .map((s) => ({
      name: s.name,
      scenarioName: s.scenario ? scenarioNameById.get(s.scenario) ?? null : null,
    }));

  const caseRows = suites.map((s) => {
    const latest = latestBySuite.get(s.name);
    return {
      name: s.name,
      source: s.source ?? null,
      target: s.target,
      latest: latest
        ? { passed: !!latest.passed, started_at: latest.started_at, run_ref: latest.run_ref }
        : null,
    };
  });

  return (
    <div>
      <PageHeader
        title={`Scenario: ${scenario.name}`}
        description={scenario.description}
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/scenarios">
              <ArrowLeft className="mr-1.5 h-4 w-4" />
              All scenarios
            </Link>
          </Button>
        }
      />
      <div className="space-y-5 p-6">
        <ScenarioRunLauncher scenarioId={scenario.id} suites={suites.map((s) => s.name)} />

        <ScenarioCasesManager scenarioId={scenario.id} cases={caseRows} available={available} />

        {/* Persisted scenario-run history */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Scenario run history <span className="font-normal text-muted-foreground">({scenarioRuns.length})</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-hidden rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>By</TableHead>
                    <TableHead>Result</TableHead>
                    <TableHead>Cases (pass / fail / error)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {scenarioRuns.map((r) => (
                    <TableRow key={r.batch_id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {fmtDateTime(r.started_at)}
                      </TableCell>
                      <TableCell className="text-sm">{r.member}</TableCell>
                      <TableCell>
                        <StatusBadge status={r.status === "passed" ? "PASS" : r.status === "error" ? "ERROR" : r.status === "failed" ? "FAIL" : "WARN"} />
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {r.rollup.cases_passed} / {r.rollup.cases_failed} / {r.rollup.cases_errored}
                        {" "}of {r.rollup.cases_total}
                      </TableCell>
                    </TableRow>
                  ))}
                  {scenarioRuns.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                        No scenario runs yet.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
