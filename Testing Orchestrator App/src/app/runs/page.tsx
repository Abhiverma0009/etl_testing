import Link from "next/link";
import { getManifest } from "@/lib/runsStore";
import { suiteScenarioNameMap } from "@/lib/scenariosStore";
import { PageHeader } from "@/components/page-header";
import { RunsTable } from "@/components/runs-table";
import { Button } from "@/components/ui/button";
import { Play } from "lucide-react";

export const dynamic = "force-dynamic";

const stem = (s?: string | null) => (s ?? "").replace(/\.ya?ml$/, "");

export default async function RunsPage() {
  const [manifest, suiteScenario] = await Promise.all([
    getManifest(),
    suiteScenarioNameMap(),
  ]);
  // suiteScenario is keyed by suite name (stem); manifest's suite carries the
  // ".yaml" filename — normalize so the table can look up each run's scenario.
  const scenarioBySuiteStem = suiteScenario;
  const runs = manifest.runs.map((r) => ({
    ...r,
    scenarioName: scenarioBySuiteStem[stem(r.suite)] ?? null,
  }));
  return (
    <div>
      <PageHeader
        title="Runs"
        description={
          manifest.count
            ? `${manifest.count} run(s)${manifest.shown < manifest.count ? ` · showing newest ${manifest.shown}` : ""}`
            : "No runs yet"
        }
        actions={
          <Button asChild size="sm">
            <Link href="/runs/new">
              <Play className="mr-1.5 h-4 w-4" />
              New run
            </Link>
          </Button>
        }
      />
      <div className="p-6">
        {manifest.runs.length === 0 ? (
          <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
            No runs recorded yet.{" "}
            <Link href="/runs/new" className="font-medium text-primary hover:underline">
              Start a run
            </Link>{" "}
            to see results here.
          </div>
        ) : (
          <RunsTable runs={runs} />
        )}
      </div>
    </div>
  );
}
