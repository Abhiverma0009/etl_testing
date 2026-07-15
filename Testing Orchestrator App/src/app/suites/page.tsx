import { listSuites, listConnections, listMappingOptions } from "@/lib/configStore";
import { listReportNames } from "@/lib/reportsStore";
import { listScenarios } from "@/lib/scenariosStore";
import { PageHeader } from "@/components/page-header";
import { SuitesManager } from "@/components/suites-manager";
import { SuitesImport } from "@/components/suites-import";
import { ALL_CATEGORIES } from "@/lib/categories";

export const dynamic = "force-dynamic";

export default async function SuitesPage() {
  const [suites, connections, mappings, reports, scenarios] = await Promise.all([
    listSuites(),
    listConnections(),
    listMappingOptions(),
    listReportNames(),
    listScenarios(),
  ]);
  return (
    <div>
      <PageHeader
        title="Suites"
        description="Validation hops — a source, a target, a mapping, and which tests to run. Each suite is a test case; group them under a Test scenario."
        actions={<SuitesImport />}
      />
      <div className="p-6">
        <SuitesManager
          suites={suites}
          connections={connections.map((c) => c.name)}
          mappings={mappings}
          categories={ALL_CATEGORIES}
          reports={reports}
          scenarios={scenarios.map((s) => ({ id: s.id, name: s.name }))}
        />
      </div>
    </div>
  );
}
