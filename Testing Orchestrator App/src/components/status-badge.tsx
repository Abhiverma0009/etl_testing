import { cn } from "@/lib/utils";

// Literal (non-dynamic) class strings so Tailwind's JIT detects them.
const STATUS_CLASS: Record<string, string> = {
  PASS: "text-status-pass border-status-pass/30 bg-status-pass/10",
  FAIL: "text-status-fail border-status-fail/30 bg-status-fail/10",
  WARN: "text-status-warn border-status-warn/30 bg-status-warn/10",
  ERROR: "text-status-error border-status-error/30 bg-status-error/10",
  SKIPPED: "text-status-skipped border-status-skipped/30 bg-status-skipped/10",
};

export function StatusBadge({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  const key = (status || "").toUpperCase();
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-bold uppercase leading-5",
        STATUS_CLASS[key] ?? STATUS_CLASS.SKIPPED,
        className,
      )}
    >
      {status}
    </span>
  );
}

// Dot-only variant for compact lists.
const DOT_CLASS: Record<string, string> = {
  PASS: "bg-status-pass",
  FAIL: "bg-status-fail",
  WARN: "bg-status-warn",
  ERROR: "bg-status-error",
  SKIPPED: "bg-status-skipped",
};

export function StatusDot({ status, className }: { status: string; className?: string }) {
  const key = (status || "").toUpperCase();
  return (
    <span
      className={cn("inline-block h-2 w-2 rounded-full", DOT_CLASS[key] ?? DOT_CLASS.SKIPPED, className)}
    />
  );
}
