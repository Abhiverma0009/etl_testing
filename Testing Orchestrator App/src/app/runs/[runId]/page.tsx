import { notFound } from "next/navigation";
import { decodeRunRef } from "@/lib/paths";
import { getRun } from "@/lib/runsStore";
import { getRunAnalytics } from "@/lib/runAnalytics";
import { CommandCenter } from "@/components/command-center";

export const dynamic = "force-dynamic";

export default async function RunDetailPage({
  params,
}: {
  params: { runId: string };
}) {
  // params.runId is a "<member>~<run_id>" ref (see paths.ts encodeRunRef) so a
  // run from any teammate's folder can be linked to unambiguously.
  const ref = decodeRunRef(params.runId);
  if (!ref) notFound();
  const run = await getRun(ref.member, ref.runId);
  if (!run) notFound();
  const analytics = await getRunAnalytics(run);
  return <CommandCenter run={run} analytics={analytics} member={ref.member} />;
}
