"use server";

import { revalidatePath } from "next/cache";
import { upsertScenario, deleteScenario } from "@/lib/scenariosStore";
import { getSuite, upsertSuite } from "@/lib/configStore";
import type { Scenario } from "@/lib/types";

function revalidateScenarioViews() {
  revalidatePath("/scenarios");
  revalidatePath("/suites");
  revalidatePath("/runs");
}

/** Set (or clear, when scenarioId is null) which scenario a suite belongs to. */
export async function setSuiteScenario(suiteName: string, scenarioId: string | null) {
  const suite = await getSuite(suiteName);
  if (!suite) throw new Error(`Suite '${suiteName}' not found`);
  if (scenarioId) suite.scenario = scenarioId;
  else delete suite.scenario;
  await upsertSuite(suite);
  revalidateScenarioViews();
}

/** Attach several suites to a scenario (moves any already in another scenario). */
export async function attachSuites(scenarioId: string, suiteNames: string[]) {
  for (const name of suiteNames) {
    const suite = await getSuite(name);
    if (!suite) continue;
    suite.scenario = scenarioId;
    await upsertSuite(suite);
  }
  revalidateScenarioViews();
}

/** Remove a suite from its scenario (it becomes Ungrouped; the suite is kept). */
export async function detachSuite(suiteName: string) {
  await setSuiteScenario(suiteName, null);
}

export async function saveScenario(sc: Scenario) {
  if (!sc.id?.trim()) throw new Error("Scenario id is required");
  if (!sc.name?.trim()) throw new Error("Scenario name is required");
  await upsertScenario({
    id: sc.id.trim().replace(/[^a-zA-Z0-9_-]/g, "_"),
    name: sc.name.trim(),
    description: sc.description?.trim() || undefined,
  });
  revalidatePath("/scenarios");
  revalidatePath("/suites");
}

export async function removeScenario(id: string) {
  await deleteScenario(id);
  revalidatePath("/scenarios");
  revalidatePath("/suites");
}
