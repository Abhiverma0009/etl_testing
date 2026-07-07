"use server";

import { revalidatePath } from "next/cache";
import { upsertSuite, deleteSuite } from "@/lib/configStore";
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
