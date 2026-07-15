"use server";

import { revalidatePath } from "next/cache";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { upsertSuite, deleteSuite } from "@/lib/configStore";
import { runEtl } from "@/lib/python";
import type { SuiteConfig } from "@/lib/types";

export async function saveSuite(suite: SuiteConfig) {
  if (!suite.name?.trim()) throw new Error("Suite name is required");
  if (!suite.target) throw new Error("A target connection is required");
  await upsertSuite({ ...suite, name: suite.name.trim() });
  revalidatePath("/suites");
  revalidatePath("/runs/new");
}

export async function removeSuite(name: string) {
  await deleteSuite(name);
  revalidatePath("/suites");
  revalidatePath("/runs/new");
}

export interface ImportSuitesResult {
  ok: boolean;
  message: string;
  created?: string[];
  updated?: string[];
  scenariosCreated?: string[];
  warnings?: string[];
}

/** Import test cases (suites) + scenarios from an Excel workbook. Saves the
 * upload to a temp file and runs the engine's `import-suites` (which parses the
 * workbook and writes config/suites/*.yaml + scenarios.yaml), then surfaces the
 * JSON summary. Keeps the app free of any Excel library. */
export async function importSuites(formData: FormData): Promise<ImportSuitesResult> {
  const file = formData.get("file");
  if (!(file instanceof File)) return { ok: false, message: "No file received." };
  if (!/\.(xlsx|xlsm)$/i.test(file.name)) {
    return { ok: false, message: "Please upload an Excel .xlsx (or .xlsm) workbook." };
  }

  const tmp = path.join(os.tmpdir(), `etl-testcases-${Date.now()}.xlsx`);
  await fs.writeFile(tmp, Buffer.from(await file.arrayBuffer()));
  try {
    const res = await runEtl(["import-suites", tmp]);
    if (res.code !== 0) {
      const detail = (res.stderr + "\n" + res.stdout)
        .split("\n").map((l) => l.trim()).filter(Boolean).slice(-4).join(" ");
      return { ok: false, message: detail || "Import failed — check the sheet format." };
    }
    // The CLI prints a single JSON summary line on stdout.
    const line = res.stdout.split("\n").map((l) => l.trim()).filter(Boolean).pop() || "{}";
    let summary: {
      created_suites?: string[]; updated_suites?: string[];
      scenarios_created?: string[]; warnings?: string[]; count?: number;
    };
    try {
      summary = JSON.parse(line);
    } catch {
      return { ok: false, message: "Import finished but produced an unreadable summary." };
    }
    revalidatePath("/suites");
    revalidatePath("/scenarios");
    revalidatePath("/runs/new");
    const created = summary.created_suites ?? [];
    const updated = summary.updated_suites ?? [];
    const n = created.length + updated.length;
    return {
      ok: true,
      message: `Imported ${n} test case${n === 1 ? "" : "s"}` +
        (summary.scenarios_created?.length
          ? `, created ${summary.scenarios_created.length} scenario(s)` : "") + ".",
      created,
      updated,
      scenariosCreated: summary.scenarios_created ?? [],
      warnings: summary.warnings ?? [],
    };
  } finally {
    await fs.rm(tmp, { force: true });
  }
}
