import { NextResponse } from "next/server";
import { TEAM_MEMBER } from "@/lib/paths";
import { readEvidenceCsv } from "@/lib/runsStore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET /api/evidence/preview?member=&runId=&path= — parsed CSV (capped) as JSON. */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const member = url.searchParams.get("member") || TEAM_MEMBER;
  const runId = url.searchParams.get("runId");
  const rel = url.searchParams.get("path");
  if (!runId || !rel) {
    return NextResponse.json({ error: "runId and path are required" }, { status: 400 });
  }
  try {
    const table = await readEvidenceCsv(member, runId, rel, 500);
    return NextResponse.json(table);
  } catch {
    return NextResponse.json({ error: "Could not read evidence file" }, { status: 404 });
  }
}
