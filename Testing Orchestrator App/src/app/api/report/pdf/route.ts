import { NextResponse } from "next/server";
import { TEAM_MEMBER } from "@/lib/paths";
import { getRun } from "@/lib/runsStore";
import { getRunAnalytics } from "@/lib/runAnalytics";
import { renderRunReportPdf } from "@/lib/pdfReport";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET /api/report/pdf?member=<name>&runId=<id> — download a run's evidence
 * report as a PDF (member defaults to this machine's own). */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const member = url.searchParams.get("member") || TEAM_MEMBER;
  const runId = url.searchParams.get("runId");
  if (!runId) {
    return NextResponse.json({ error: "runId is required" }, { status: 400 });
  }

  const run = await getRun(member, runId);
  if (!run) {
    return NextResponse.json({ error: "Run not found" }, { status: 404 });
  }

  const analytics = await getRunAnalytics(run);
  const pdf = await renderRunReportPdf(run, analytics, member);

  return new NextResponse(new Uint8Array(pdf), {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="run-${runId}.pdf"`,
    },
  });
}
