"use server";

import { revalidatePath } from "next/cache";
import { promises as fs } from "node:fs";
import path from "node:path";
import { saveMapping, type MappingBook } from "@/lib/configStore";
import { MAPPINGS_DIR } from "@/lib/paths";
import { runEtl } from "@/lib/python";

export async function saveMappingBook(name: string, book: MappingBook) {
  await saveMapping(name, book);
  revalidatePath(`/mappings/${name}`);
  revalidatePath("/mappings");
}

export interface ImportResult {
  ok: boolean;
  name?: string;
  message: string;
}

/** Derive a safe mapping name (used as the on-disk filename stem) from the
 * uploaded workbook's filename — strip the path/extension and any character
 * that isn't safe in a filename, so a name can never escape MAPPINGS_DIR. */
function sanitizeStem(filename: string): string {
  const base = path.basename(filename).replace(/\.(xlsx|xlsm)$/i, "");
  return base.trim().replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._-]+|[._-]+$/g, "");
}

/** Import an Excel mapping workbook: save the .xlsx into config/mappings/ and
 * parse it into the app-readable .json via the engine's own Excel parser
 * (`etl-test export-mapping`), so what the app shows matches exactly what a run
 * would load. On a bad workbook, the parser's error is surfaced to the UI. */
export async function importMapping(formData: FormData): Promise<ImportResult> {
  const file = formData.get("file");
  if (!(file instanceof File)) return { ok: false, message: "No file received." };
  if (!/\.(xlsx|xlsm)$/i.test(file.name)) {
    return { ok: false, message: "Please upload an Excel .xlsx (or .xlsm) workbook." };
  }
  const name = sanitizeStem(file.name);
  if (!name) return { ok: false, message: "Could not derive a valid name from the filename." };

  await fs.mkdir(MAPPINGS_DIR, { recursive: true });
  const xlsxPath = path.join(MAPPINGS_DIR, `${name}.xlsx`);
  await fs.writeFile(xlsxPath, Buffer.from(await file.arrayBuffer()));

  // Canonical parse → writes <name>.json alongside the .xlsx (same shape the
  // app's Mappings list reads and the engine loads at run time).
  const res = await runEtl(["export-mapping", xlsxPath]);
  if (res.code !== 0) {
    // Half-imported workbook is worse than none — remove the file we just wrote.
    await fs.rm(xlsxPath, { force: true });
    const detail = (res.stderr + "\n" + res.stdout)
      .split("\n").map((l) => l.trim()).filter(Boolean).slice(-4).join(" ");
    return { ok: false, message: detail || "Failed to parse the workbook — check the sheet format." };
  }

  revalidatePath("/mappings");
  revalidatePath(`/mappings/${name}`);
  return { ok: true, name, message: `Imported "${name}".` };
}
