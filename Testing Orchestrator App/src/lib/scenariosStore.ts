/**
 * Test-scenario registry store (server-only). A scenario is the top level of QA
 * planning; it groups multiple suites (test cases). Scenario objects live in
 * config/scenarios.yaml (id → {name, description}); which suite belongs to which
 * scenario lives on the suite itself (suite.scenario), so membership has a single
 * source of truth. No database — plain YAML via the pure-JS `yaml` package.
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import YAML from "yaml";
import { SCENARIOS_PATH } from "./paths";
import { listSuites } from "./configStore";
import type { Scenario, SuiteConfig } from "./types";

export const UNGROUPED = "__ungrouped__";

interface ScenariosFile {
  scenarios: Record<string, { name?: string; description?: string }>;
}

async function readFile(): Promise<ScenariosFile> {
  try {
    const text = await fs.readFile(SCENARIOS_PATH, "utf-8");
    const doc = (YAML.parse(text) ?? {}) as ScenariosFile;
    return { scenarios: doc.scenarios ?? {} };
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return { scenarios: {} };
    throw err;
  }
}

async function writeFile(doc: ScenariosFile): Promise<void> {
  await fs.mkdir(path.dirname(SCENARIOS_PATH), { recursive: true });
  await fs.writeFile(SCENARIOS_PATH, YAML.stringify(doc), "utf-8");
}

export async function listScenarios(): Promise<Scenario[]> {
  const doc = await readFile();
  return Object.entries(doc.scenarios)
    .map(([id, s]) => ({ id, name: s.name ?? id, description: s.description }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export async function getScenario(id: string): Promise<Scenario | null> {
  return (await listScenarios()).find((s) => s.id === id) ?? null;
}

export async function upsertScenario(sc: Scenario): Promise<void> {
  const doc = await readFile();
  doc.scenarios[sc.id] = { name: sc.name, description: sc.description };
  await writeFile(doc);
}

export async function deleteScenario(id: string): Promise<void> {
  const doc = await readFile();
  delete doc.scenarios[id];
  await writeFile(doc);
}

/** All suites (test cases) belonging to one scenario, sorted by name. */
export async function suitesInScenario(id: string): Promise<SuiteConfig[]> {
  const suites = await listSuites();
  return suites
    .filter((s) => (s.scenario ?? UNGROUPED) === id)
    .sort((a, b) => a.name.localeCompare(b.name));
}

export interface ScenarioGroup {
  scenario: Scenario;
  suites: SuiteConfig[];
}

/**
 * Every scenario in the registry with its suites, plus a synthetic "Ungrouped"
 * group for suites carrying no (or an unknown) scenario tag — so nothing is
 * hidden from the UI.
 */
export async function suitesByScenario(): Promise<ScenarioGroup[]> {
  const [scenarios, suites] = await Promise.all([listScenarios(), listSuites()]);
  const known = new Set(scenarios.map((s) => s.id));
  const groups: ScenarioGroup[] = scenarios.map((scenario) => ({
    scenario,
    suites: suites
      .filter((s) => s.scenario === scenario.id)
      .sort((a, b) => a.name.localeCompare(b.name)),
  }));
  const ungrouped = suites
    .filter((s) => !s.scenario || !known.has(s.scenario))
    .sort((a, b) => a.name.localeCompare(b.name));
  if (ungrouped.length) {
    groups.push({
      scenario: { id: UNGROUPED, name: "Ungrouped", description: "Suites with no scenario assigned." },
      suites: ungrouped,
    });
  }
  return groups;
}

/** Map of suite name → scenario name, for annotating the runs list. */
export async function suiteScenarioNameMap(): Promise<Record<string, string>> {
  const [scenarios, suites] = await Promise.all([listScenarios(), listSuites()]);
  const nameById = new Map(scenarios.map((s) => [s.id, s.name]));
  const out: Record<string, string> = {};
  for (const s of suites) {
    if (s.scenario && nameById.has(s.scenario)) out[s.name] = nameById.get(s.scenario)!;
  }
  return out;
}
