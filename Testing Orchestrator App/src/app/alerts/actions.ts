"use server";

import { revalidatePath } from "next/cache";
import { saveAlertConfig, type AlertConfig } from "@/lib/alerts";

export async function updateAlertConfig(cfg: AlertConfig) {
  await saveAlertConfig(cfg);
  revalidatePath("/alerts");
}
