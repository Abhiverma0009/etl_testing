import Link from "next/link";
import { listMappingNames, getMapping } from "@/lib/configStore";
import { PageHeader } from "@/components/page-header";
import { MappingUpload } from "@/components/mapping-upload";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChevronRight } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function MappingsPage() {
  const names = await listMappingNames();
  const books = await Promise.all(
    names.map(async (n) => ({ name: n, book: await getMapping(n) })),
  );

  return (
    <div>
      <PageHeader
        title="Mappings"
        description="Source-to-target mapping books (imported from Excel, edited here as JSON)."
        actions={<MappingUpload />}
      />
      <div className="grid gap-3 p-6 sm:grid-cols-2 lg:grid-cols-3">
        {books.map(({ name, book }) => (
          <Link key={name} href={`/mappings/${name}`}>
            <Card className="transition-colors hover:border-primary">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-base">
                  {name}
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                {book
                  ? `${book.tables.length} table(s) · ${book.business_rules.length} rule(s) · ${book.ref_integrity.length} FK`
                  : "unreadable"}
              </CardContent>
            </Card>
          </Link>
        ))}
        {books.length === 0 && (
          <div className="col-span-full rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
            No mapping books yet. Use{" "}
            <span className="font-medium text-foreground">Import mapping (.xlsx)</span>{" "}
            above to add one from an Excel workbook.
          </div>
        )}
      </div>
    </div>
  );
}
