"use server";

import { revalidatePath } from "next/cache";
import { saveReport, deleteReport, type ReportBook } from "@/lib/reportsStore";

export async function saveReportBook(book: ReportBook) {
  if (!book.id?.trim()) throw new Error("Report id is required");
  if (!book.name?.trim()) throw new Error("Report name is required");
  await saveReport({ ...book, id: book.id.trim(), name: book.name.trim() });
  revalidatePath("/reports");
  revalidatePath(`/reports/${book.id.trim()}`);
  revalidatePath("/suites");
}

export async function removeReportBook(id: string) {
  await deleteReport(id);
  revalidatePath("/reports");
  revalidatePath("/suites");
}
