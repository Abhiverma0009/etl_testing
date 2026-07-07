import { getAlertConfig, listAlerts } from "@/lib/alerts";
import { listSuiteNames } from "@/lib/configStore";
import { PageHeader } from "@/components/page-header";
import { AlertsManager } from "@/components/alerts-manager";

export const dynamic = "force-dynamic";

export default async function AlertsPage() {
  const [config, alerts, suites] = await Promise.all([
    getAlertConfig(),
    listAlerts(),
    listSuiteNames(),
  ]);

  return (
    <div>
      <PageHeader
        title="Alerts"
        description="Data-quality alerts. When a run trips the rules below, a summary is posted to Teams via a Power Automate webhook and recorded here."
      />
      <div className="p-6">
        <AlertsManager config={config} alerts={alerts} suites={suites} />
      </div>
    </div>
  );
}
