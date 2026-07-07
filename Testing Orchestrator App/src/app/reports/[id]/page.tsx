import Link from "next/link";
import { notFound } from "next/navigation";
import { getReport } from "@/lib/reportsStore";
import { listConnections } from "@/lib/configStore";
import { TEAM_MEMBER } from "@/lib/paths";
import { PageHeader } from "@/components/page-header";
import { ReportEditor } from "@/components/report-editor";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function ReportPage({
  params,
}: {
  params: { id: string };
}) {
  const [report, connections] = await Promise.all([
    getReport(params.id),
    listConnections(),
  ]);
  if (!report) notFound();

  return (
    <div>
      <PageHeader
        title={`Report: ${report.name}`}
        description="Each tab compares the new Snowflake query (ACTUAL) with the legacy Access ValDB query (EXPECTED)."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/reports">
              <ArrowLeft className="mr-1.5 h-4 w-4" />
              All reports
            </Link>
          </Button>
        }
      />
      <div className="p-6">
        <ReportEditor
          report={report}
          connections={connections.map((c) => c.name)}
          member={TEAM_MEMBER}
        />
      </div>
    </div>
  );
}
