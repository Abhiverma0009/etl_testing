import { sseBatchResponse } from "@/lib/sse";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: { batchId: string } },
) {
  return sseBatchResponse(params.batchId);
}
