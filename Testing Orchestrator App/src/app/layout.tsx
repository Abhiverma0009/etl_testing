import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { cn } from "@/lib/utils";
import { Nav } from "@/components/nav";
import { Toaster } from "@/components/ui/sonner";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "ETL Test Console",
  description: "Run and review the ETL migration consistency & integrity tests.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={cn(sans.variable, mono.variable)} suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <div className="flex min-h-screen">
          <aside className="hidden w-[200px] shrink-0 flex-col border-r border-[#e6e8ee] bg-white py-5 md:flex">
            <div className="px-5 pb-[18px]">
              <Link href="/runs" className="block">
                <div className="text-[13px] font-bold tracking-[.04em] text-[#101828]">
                  ETL TEST CONSOLE
                </div>
                {/* <div className="mt-0.5 text-[10px] tracking-[.1em] text-[#98a2b3]">
                  ETL TEST CONSOLE
                </div> */}
              </Link>
            </div>
            <Nav />
          </aside>
          <main className="min-w-0 flex-1">{children}</main>
        </div>
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
}
