"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/runs", label: "Runs" },
  { href: "/runs/new", label: "New run" },
  { href: "/scenarios", label: "Scenarios" },
  { href: "/connections", label: "Connections" },
  { href: "/suites", label: "Suites" },
  { href: "/mappings", label: "Mappings" },
  { href: "/reports", label: "Reports" },
  { href: "/alerts", label: "Alerts" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <div className="flex flex-col gap-0.5">
      {ITEMS.map(({ href, label }) => {
        const active =
          href === "/runs/new"
            ? pathname === "/runs/new"
            : href === "/runs"
              ? pathname === "/runs" || /^\/runs\/(?!new)[^/]+/.test(pathname)
              : pathname === href || pathname.startsWith(href + "/");
        return (
          <Link
            key={href}
            href={href}
            className="mx-2.5 flex items-center gap-2.5 rounded-[7px] px-3 py-2 text-[13px] font-medium hover:bg-[#f1f3f7]"
            style={{
              color: active ? "#2a5fdb" : "#475467",
              background: active ? "#eef4ff" : "transparent",
            }}
          >
            <span
              className="h-1.5 w-1.5 rounded-[2px]"
              style={{ background: active ? "#2a5fdb" : "#c2c9d4" }}
            />
            {label}
          </Link>
        );
      })}
    </div>
  );
}
