/**
 * Flat-file store for report definitions (server-only). Each report is one
 * config/reports/<id>.json file describing a report (GVC, MD&A, …) as a list of
 * tabs, every tab a legacy-vs-new query pair. Mirrors the Python-side shape
 * consumed by etl_test.reporting.reports.load_reports.
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import { REPORTS_DIR } from "./paths";

export interface ReportSide {
  connection?: string;
  query?: string;
  table?: string;
  where?: string;
  columns?: string[];
}

export interface ReportMeasure {
  label?: string;
  column: string;
  tolerance?: number;
}

export interface ReportTab {
  name: string;
  key_columns: string[];
  compare_columns?: string[];
  measures?: ReportMeasure[];
  severity?: string;
  actual: ReportSide; // new / Snowflake side
  expected: ReportSide; // legacy / Access side
}

export interface ReportBook {
  id: string;
  name: string;
  type?: string; // GVC | MDA | SIS | ...
  expected_connection?: string; // per-report default (legacy side)
  actual_connection?: string; // per-report default (new side)
  tabs: ReportTab[];
}

function reportPath(id: string): string {
  return path.join(REPORTS_DIR, `${id}.json`);
}

export async function listReportNames(): Promise<string[]> {
  try {
    const files = await fs.readdir(REPORTS_DIR);
    return files
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.replace(/\.json$/, ""))
      .sort();
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
}

export async function getReport(id: string): Promise<ReportBook | null> {
  try {
    const text = await fs.readFile(reportPath(id), "utf-8");
    const data = JSON.parse(text);
    return {
      id: data.id ?? id,
      name: data.name ?? id,
      type: data.type,
      expected_connection: data.expected_connection,
      actual_connection: data.actual_connection,
      tabs: (data.tabs ?? []) as ReportTab[],
    };
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}

export async function listReports(): Promise<ReportBook[]> {
  const names = await listReportNames();
  const books = await Promise.all(names.map((n) => getReport(n)));
  return books.filter((b): b is ReportBook => b !== null);
}

export async function saveReport(book: ReportBook): Promise<void> {
  await fs.mkdir(REPORTS_DIR, { recursive: true });
  await fs.writeFile(reportPath(book.id), JSON.stringify(book, null, 2), "utf-8");
}

export async function deleteReport(id: string): Promise<void> {
  try {
    await fs.unlink(reportPath(id));
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
  }
}

/** The target connection to run a report against (its ACTUAL / Snowflake side). */
export function reportTarget(book: ReportBook): string | null {
  return (
    book.actual_connection ||
    book.tabs.map((t) => t.actual?.connection).find(Boolean) ||
    null
  );
}
