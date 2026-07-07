"use server";

import { revalidatePath } from "next/cache";
import {
  upsertConnection,
  deleteConnection,
} from "@/lib/configStore";
import { runEtl } from "@/lib/python";
import type { ConnectionConfig } from "@/lib/types";

export async function saveConnection(conn: ConnectionConfig) {
  if (!conn.name?.trim()) throw new Error("Connection name is required");
  // Drop empty-string fields so we don't write noise into the YAML.
  const cleaned: ConnectionConfig = { name: conn.name.trim(), type: conn.type };
  for (const [k, v] of Object.entries(conn)) {
    if (k === "name" || k === "type") continue;
    if (v === "" || v === undefined || v === null) continue;
    cleaned[k] = v;
  }
  await upsertConnection(cleaned);
  revalidatePath("/connections");
  revalidatePath("/runs/new");
}

export async function removeConnection(name: string) {
  await deleteConnection(name);
  revalidatePath("/connections");
}

export async function testConnection(
  name: string,
): Promise<{ ok: boolean; message: string }> {
  const res = await runEtl(["test-connection", name]);
  const ok = res.code === 0;
  const combined = (res.stdout + "\n" + res.stderr)
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const message = combined.slice(-3).join(" ") || (ok ? "OK" : "Failed");
  return { ok, message };
}
