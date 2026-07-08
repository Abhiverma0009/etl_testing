import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";
import "./globals.css";
import { cn } from "@/lib/utils";
import { Nav } from "@/components/nav";
import { Toaster } from "@/components/ui/sonner";

// Self-hosted IBM Plex fonts (files committed under ./fonts). Using
// next/font/local instead of next/font/google so the app builds and runs on a
// locked-down VM with no internet — next/font/google fetches from Google Fonts
// at build/dev time, which fails offline. Weights match the prior google setup.
const sans = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-sans-600.woff2", weight: "600", style: "normal" },
    { path: "./fonts/ibm-plex-sans-700.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-sans",
  display: "swap",
});
const mono = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-mono-600.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-mono",
  display: "swap",
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
