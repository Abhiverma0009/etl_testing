import Link from "next/link";
import { notFound } from "next/navigation";
import { getMapping } from "@/lib/configStore";
import { PageHeader } from "@/components/page-header";
import { MappingEditor } from "@/components/mapping-editor";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function MappingBookPage({
  params,
}: {
  params: { book: string };
}) {
  const book = await getMapping(params.book);
  if (!book) notFound();

  return (
    <div>
      <PageHeader
        title={`Mapping: ${params.book}`}
        description="Tables, columns, business rules and referential integrity."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/mappings">
              <ArrowLeft className="mr-1.5 h-4 w-4" />
              All mappings
            </Link>
          </Button>
        }
      />
      <div className="p-6">
        <MappingEditor name={params.book} book={book} />
      </div>
    </div>
  );
}
