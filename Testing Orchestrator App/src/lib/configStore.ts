/**
 * Flat-file config store (server-only). Reads/writes the same files the Python
 * CLI consumes: config/connections.yaml, config/suites/*.yaml, and the app-owned
 * config/mappings/<name>.json. No database.
 *
 * Secrets are never resolved here — connection secret fields stay as literal
 * "${VAR}" strings; the UI only edits the referenced env-var name.
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import YAML from "yaml";
import {
  CONNECTIONS_PATH,
  SUITES_DIR,
  MAPPINGS_DIR,
} from "./paths";
import type { ConnectionConfig, SuiteConfig } from "./types";

async function readYaml<T = unknown>(file: string): Promise<T | null> {
  try {
    const text = await fs.readFile(file, "utf-8");
    return (YAML.parse(text) ?? null) as T;
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}

async function writeYaml(file: string, data: unknown): Promise<void> {
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, YAML.stringify(data), "utf-8");
}

// ---------------- Connections ----------------
interface ConnectionsFile {
  connections: Record<string, Record<string, unknown>>;
}

export async function listConnections(): Promise<ConnectionConfig[]> {
  const doc = await readYaml<ConnectionsFile>(CONNECTIONS_PATH);
  const conns = doc?.connections ?? {};
  return Object.entries(conns).map(([name, cfg]) => ({
    name,
    type: (cfg.type as ConnectionConfig["type"]) ?? "snowflake",
    ...cfg,
  }));
}

export async function getConnection(name: string): Promise<ConnectionConfig | null> {
  return (await listConnections()).find((c) => c.name === name) ?? null;
}

export async function upsertConnection(conn: ConnectionConfig): Promise<void> {
  const doc = (await readYaml<ConnectionsFile>(CONNECTIONS_PATH)) ?? { connections: {} };
  if (!doc.connections) doc.connections = {};
  const { name, ...rest } = conn;
  doc.connections[name] = rest;
  await writeYaml(CONNECTIONS_PATH, doc);
}

export async function deleteConnection(name: string): Promise<void> {
  const doc = await readYaml<ConnectionsFile>(CONNECTIONS_PATH);
  if (!doc?.connections) return;
  delete doc.connections[name];
  await writeYaml(CONNECTIONS_PATH, doc);
}

// ---------------- Suites ----------------
function suitePath(name: string): string {
  return path.join(SUITES_DIR, `${name}.yaml`);
}

export async function listSuiteNames(): Promise<string[]> {
  try {
    const files = await fs.readdir(SUITES_DIR);
    return files
      .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"))
      .map((f) => f.replace(/\.ya?ml$/, ""))
      .sort();
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
}

export async function getSuite(name: string): Promise<SuiteConfig | null> {
  const doc = await readYaml<Record<string, unknown>>(suitePath(name));
  if (!doc) return null;
  return { name, ...(doc as object) } as SuiteConfig;
}

export async function listSuites(): Promise<SuiteConfig[]> {
  const names = await listSuiteNames();
  const suites = await Promise.all(names.map((n) => getSuite(n)));
  return suites.filter((s): s is SuiteConfig => s !== null);
}

export async function upsertSuite(suite: SuiteConfig): Promise<void> {
  const { name, ...body } = suite;
  await writeYaml(suitePath(name), body);
}

export async function deleteSuite(name: string): Promise<void> {
  try {
    await fs.unlink(suitePath(name));
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
  }
}

// ---------------- Mappings (app-owned JSON) ----------------
function mappingPath(name: string): string {
  return path.join(MAPPINGS_DIR, `${name}.json`);
}

export async function listMappingNames(): Promise<string[]> {
  try {
    const files = await fs.readdir(MAPPINGS_DIR);
    return files
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.replace(/\.json$/, ""))
      .sort();
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
}

export interface MappingOption {
  name: string;
  path: string; // repo-relative path a suite's `mapping:` should point at
}

/** Every mapping (by name) with the best on-disk path to reference it. Prefers
 * the live Excel workbook (`.xlsx`/`.xlsm`) so edits take effect immediately;
 * falls back to the exported `.json`. Used to populate the suite editor's
 * mapping picker with paths that actually exist and won't corrupt on save. */
export async function listMappingOptions(): Promise<MappingOption[]> {
  let files: string[] = [];
  try {
    files = await fs.readdir(MAPPINGS_DIR);
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
  const excelFile = new Map<string, string>(); // name -> actual excel filename
  const jsonNames = new Set<string>();
  for (const f of files) {
    const mx = /^(.*)\.(xlsx|xlsm)$/i.exec(f);
    if (mx) { excelFile.set(mx[1], f); continue; }
    const mj = /^(.*)\.json$/i.exec(f);
    if (mj) jsonNames.add(mj[1]);
  }
  const names = new Set<string>([...excelFile.keys(), ...jsonNames]);
  return [...names].sort().map((name) => ({
    name,
    path: excelFile.has(name)
      ? `config/mappings/${excelFile.get(name)}`
      : `config/mappings/${name}.json`,
  }));
}

export interface MappingColumn {
  target_table: string;
  target_column: string;
  source_column?: string | null;
  source_datatype?: string | null;
  target_datatype?: string | null;
  nullable?: boolean;
  transformation?: string | null;
  default_value?: unknown;
  compare?: boolean;
  case_sensitive?: boolean;
  numeric_tolerance?: number | null;
  is_key?: boolean;
}

export interface MappingTable {
  target_table: string;
  source_system?: string | null;
  source_object?: string | null;
  target_db?: string | null;
  target_schema?: string | null;
  layer?: string | null;
  load_type?: string;
  source_object_type?: string; // "table" | "view" — descriptive; engine reads both identically
  target_object_type?: string; // "table" | "view"
  key_columns?: string[];
  active?: boolean;
  columns?: MappingColumn[];
  options?: Record<string, unknown>;
}

export interface BusinessRule {
  rule_id: string;
  target_table: string;
  rule_type: string;
  params?: Record<string, unknown>;
  filter?: string | null;
  severity?: string;
  use_case?: string | null;
  description?: string;
  active?: boolean;
}

export interface RefIntegrityRule {
  child_table: string;
  child_columns: string[];
  parent_table: string;
  parent_columns: string[];
  severity?: string;
  description?: string;
  active?: boolean;
}

export interface MappingBook {
  source_file?: string;
  tables: MappingTable[];
  business_rules: BusinessRule[];
  ref_integrity: RefIntegrityRule[];
  warnings?: string[];
}

export async function getMapping(name: string): Promise<MappingBook | null> {
  try {
    const text = await fs.readFile(mappingPath(name), "utf-8");
    const data = JSON.parse(text);
    return {
      source_file: data.source_file,
      tables: data.tables ?? [],
      business_rules: data.business_rules ?? [],
      ref_integrity: data.ref_integrity ?? [],
      warnings: data.warnings ?? [],
    };
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}

export async function saveMapping(name: string, book: MappingBook): Promise<void> {
  await fs.mkdir(MAPPINGS_DIR, { recursive: true });
  await fs.writeFile(mappingPath(name), JSON.stringify(book, null, 2), "utf-8");
}
