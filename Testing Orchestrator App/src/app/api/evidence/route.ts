import { NextResponse } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";
import { TEAM_MEMBER, memberRunDir, memberEvidenceAbsPath } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET /api/evidence?member=<name>&runId=<id>&path=<relative csv> — download an
 * evidence CSV from any team member's run (member defaults to this machine's own). */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const member = url.searchParams.get("member") || TEAM_MEMBER;
  const runId = url.searchParams.get("runId");
  const rel = url.searchParams.get("path");
  if (!runId || !rel) {
    return NextResponse.json({ error: "runId and path are required" }, { status: 400 });
  }

  const abs = path.resolve(memberEvidenceAbsPath(member, runId, rel));
  const base = path.resolve(memberRunDir(member, runId));
  // Guard against path traversal outside the run directory.
  if (!abs.startsWith(base + path.sep) && abs !== base) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  try {
    const data = await fs.readFile(abs);
    return new NextResponse(data, {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="${path.basename(abs)}"`,
      },
    });
  } catch {
    return NextResponse.json({ error: "File not found" }, { status: 404 });
  }
}
