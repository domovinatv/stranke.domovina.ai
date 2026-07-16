import type { PartyStatus } from "@/lib/types";

const STYLES: Record<string, { cls: string; dot: string; label: string }> = {
  AKTIVAN: {
    cls: "bg-emerald-50 text-emerald-700 border-emerald-200",
    dot: "bg-emerald-500",
    label: "Aktivna",
  },
  PRESTANAK: {
    cls: "bg-slate-100 text-slate-600 border-slate-200",
    dot: "bg-slate-400",
    label: "Ugašena",
  },
  UNKNOWN: {
    cls: "bg-amber-50 text-amber-700 border-amber-200",
    dot: "bg-amber-500",
    label: "Nepoznat",
  },
};

export function StatusBadge({
  status,
  size = "sm",
}: {
  status?: PartyStatus;
  size?: "xs" | "sm" | "md";
}) {
  const s = STYLES[status ?? "UNKNOWN"] ?? STYLES.UNKNOWN;
  const pad =
    size === "md"
      ? "px-3 py-1 text-sm"
      : size === "xs"
        ? "px-2 py-px text-[11px]"
        : "px-2.5 py-0.5 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium whitespace-nowrap ${pad} ${s.cls}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${s.dot}`}
        aria-hidden="true"
      />
      {s.label}
    </span>
  );
}
