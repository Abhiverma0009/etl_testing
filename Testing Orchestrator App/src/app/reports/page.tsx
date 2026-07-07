import { listReports } from "@/lib/reportsStore";
import { listConnections } from "@/lib/configStore";
import { PageHeader } from "@/components/page-header";
import { ReportsManager } from "@/components/reports-manager";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const [reports, connections] = await Promise.all([
    listReports(),
    listConnections(),
  ]);

  return (
    <div>
      <PageHeader
        title="Reports"
        description="GVC / MD&A report tests — each tab compares the new Snowflake query (ACTUAL) against the legacy Access ValDB query (EXPECTED)."
      />
      <div className="p-6">
        <ReportsManager
          reports={reports.map((r) => ({
            id: r.id,
            name: r.name,
            type: r.type ?? "",
            tabs: r.tabs.length,
            actual_connection: r.actual_connection ?? "",
            expected_connection: r.expected_connection ?? "",
          }))}
          connections={connections.map((c) => c.name)}
        />
      </div>
    </div>
  );
}
