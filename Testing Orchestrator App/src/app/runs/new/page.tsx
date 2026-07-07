import { listSuites } from "@/lib/configStore";
import { TEAM_MEMBER } from "@/lib/paths";
import { PageHeader } from "@/components/page-header";
import { RunLauncher } from "@/components/run-launcher";
import { ALL_CATEGORIES } from "@/lib/categories";

export const dynamic = "force-dynamic";

export default async function NewRunPage() {
  const suites = await listSuites();
  return (
    <div>
      <PageHeader
        title="New run"
        description="Trigger a suite and watch progress stream live."
      />
      <div className="max-w-3xl p-6">
        <RunLauncher
          suites={suites.map((s) => ({
            name: s.name,
            source: s.source ?? null,
            target: s.target,
            tests: s.tests ?? [],
          }))}
          categories={ALL_CATEGORIES}
          member={TEAM_MEMBER}
        />
      </div>
    </div>
  );
}
