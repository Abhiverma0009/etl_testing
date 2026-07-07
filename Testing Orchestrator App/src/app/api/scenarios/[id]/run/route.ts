import { NextResponse } from "next/server";
import path from "node:path";
import { getScenario, suitesInScenario } from "@/lib/scenariosStore";
import { isAnyRunActive, startScenarioRun } from "@/lib/runManager";
import { SUITES_DIR } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** POST /api/scenarios/<id>/run — run every test case (suite) in the scenario. */
export async function POST(_req: Request, { params }: { params: { id: string } }) {
  const scenarioId = params.id;

  if (isAnyRunActive()) {
    return NextResponse.json(
      { error: "A run is already in progress. Wait for it to finish." },
      { status: 409 },
    );
  }

  const scenario = await getScenario(scenarioId);
  if (!scenario) {
    return NextResponse.json({ error: `Scenario '${scenarioId}' not found.` }, { status: 404 });
  }

  const suites = await suitesInScenario(scenarioId);
  if (suites.length === 0) {
    return NextResponse.json(
      { error: `Scenario '${scenario.name}' has no test cases (suites) yet.` },
      { status: 400 },
    );
  }

  const batchId = startScenarioRun({
    scenarioId,
    scenarioName: scenario.name,
    cases: suites.map((s) => ({
      suiteName: s.name,
      suitePath: path.join(SUITES_DIR, `${s.name}.yaml`),
    })),
  });

  return NextResponse.json({ batchId, cases: suites.map((s) => s.name) });
}
