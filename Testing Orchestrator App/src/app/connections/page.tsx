import { listConnections } from "@/lib/configStore";
import { PageHeader } from "@/components/page-header";
import { ConnectionsManager } from "@/components/connections-manager";

export const dynamic = "force-dynamic";

export default async function ConnectionsPage() {
  const connections = await listConnections();
  return (
    <div>
      <PageHeader
        title="Connections"
        description="Data sources & targets. Secrets stay in .env — referenced here as ${VAR}."
      />
      <div className="p-6">
        <ConnectionsManager connections={connections} />
      </div>
    </div>
  );
}
