"use server";

import { revalidatePath } from "next/cache";
import { saveMapping, type MappingBook } from "@/lib/configStore";

export async function saveMappingBook(name: string, book: MappingBook) {
  await saveMapping(name, book);
  revalidatePath(`/mappings/${name}`);
  revalidatePath("/mappings");
}
