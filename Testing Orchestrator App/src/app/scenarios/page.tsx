import { suitesByScenario, UNGROUPED } from "@/lib/scenariosStore";
import { PageHeader } from "@/components/page-header";
import { ScenariosManager } from "@/components/scenarios-manager";

export const dynamic = "force-dynamic";

export default async function ScenariosPage() {
  const groups = await suitesByScenario();
  const rows = groups
    .filter((g) => g.scenario.id !== UNGROUPED)
    .map((g) => ({
      id: g.scenario.id,
      name: g.scenario.name,
      description: g.scenario.description,
      caseCount: g.suites.length,
    }));

  return (
    <div>
      <PageHeader
        title="Test scenarios"
        description="The top level of QA planning. A scenario groups multiple test cases (suites); run every case in a scenario at once."
      />
      <div className="p-6">
        <ScenariosManager scenarios={rows} />
      </div>
    </div>
  );
}
