import { NextResponse } from "next/server";
import path from "node:path";
import { promises as fs } from "node:fs";
import YAML from "yaml";
import { getSuite } from "@/lib/configStore";
import { getReport, reportTarget } from "@/lib/reportsStore";
import { isAnyRunActive, startRun } from "@/lib/runManager";
import { SUITES_DIR, RUNSUITES_DIR } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface StartBody {
  suiteName?: string;
  reportId?: string;
  tests?: string[];
  tables?: string[];
}

/** Write an ephemeral report-only suite and return its path. */
async function writeReportSuite(reportId: string, target: string): Promise<string> {
  await fs.mkdir(RUNSUITES_DIR, { recursive: true });
  const p = path.join(RUNSUITES_DIR, `report_${reportId}.yaml`);
  await fs.writeFile(
    p,
    YAML.stringify({ target, reports: [reportId], tests: ["report"] }),
    "utf-8",
  );
  return p;
}

export async function POST(req: Request) {
  let body: StartBody;
  try {
    body = (await req.json()) as StartBody;
  } catch {
    body = {};
  }

  const reportId = body.reportId?.trim();
  const suiteName = body.suiteName?.trim();
  if (!reportId && !suiteName) {
    return NextResponse.json(
      { error: "suiteName or reportId is required" },
      { status: 400 },
    );
  }

  // Single-user local tool: serialize runs to avoid concurrent DB/Access reads.
  if (isAnyRunActive()) {
    return NextResponse.json(
      { error: "A run is already in progress. Wait for it to finish." },
      { status: 409 },
    );
  }

  // One-click report run: synthesize an ephemeral report-only suite.
  if (reportId) {
    const report = await getReport(reportId);
    if (!report) {
      return NextResponse.json(
        { error: `Report '${reportId}' not found.` },
        { status: 404 },
      );
    }
    const target = reportTarget(report);
    if (!target) {
      return NextResponse.json(
        { error: `Report '${reportId}' has no ACTUAL (Snowflake) connection set.` },
        { status: 400 },
      );
    }
    const suitePath = await writeReportSuite(reportId, target);
    const jobId = startRun({ suitePath, suiteName: `report:${report.name}` });
    return NextResponse.json({ jobId });
  }

  const suite = await getSuite(suiteName!);
  if (!suite) {
    return NextResponse.json(
      { error: `Suite '${suiteName}' not found.` },
      { status: 404 },
    );
  }

  const suitePath = path.join(SUITES_DIR, `${suiteName}.yaml`);
  const jobId = startRun({
    suitePath,
    suiteName,
    tests: body.tests,
    tables: body.tables,
  });

  return NextResponse.json({ jobId });
}

export async function GET() {
  return NextResponse.json({ active: isAnyRunActive() });
}
