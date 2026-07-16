import type { Party } from "@/lib/types";

/**
 * Stranke nemaju logotipe u katalogu, pa svaka dobiva inicijal-avatar:
 * prvo slovo kraćeg (ili punog) naziva na pozadini deterministički
 * izvedenoj iz canonical_name — ista stranka uvijek ima istu boju.
 */
const PALETTE: Array<{ bg: string; fg: string }> = [
  { bg: "#0EA5E9", fg: "#FFFFFF" }, // sky-500
  { bg: "#6366F1", fg: "#FFFFFF" }, // indigo-500
  { bg: "#8B5CF6", fg: "#FFFFFF" }, // violet-500
  { bg: "#EC4899", fg: "#FFFFFF" }, // pink-500
  { bg: "#F43F5E", fg: "#FFFFFF" }, // rose-500
  { bg: "#F97316", fg: "#FFFFFF" }, // orange-500
  { bg: "#EAB308", fg: "#3F3000" }, // yellow-500
  { bg: "#10B981", fg: "#FFFFFF" }, // emerald-500
  { bg: "#14B8A6", fg: "#FFFFFF" }, // teal-500
  { bg: "#64748B", fg: "#FFFFFF" }, // slate-500
];

function hashString(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) {
    h = (h * 33) ^ s.charCodeAt(i);
  }
  return h >>> 0;
}

function initialOf(party: Pick<Party, "short_name" | "canonical_name">): string {
  const source = party.short_name || party.canonical_name || "?";
  // Skip quotes and other non-letter prefixes ("DO i SIP" → D).
  const m = source.match(/\p{L}/u);
  return (m ? m[0] : "?").toUpperCase();
}

export function partyColor(
  party: Pick<Party, "canonical_name">,
): { bg: string; fg: string } {
  return PALETTE[hashString(party.canonical_name || "") % PALETTE.length];
}

export function PartyAvatar({
  party,
  size = 48,
  className = "",
}: {
  party: Pick<Party, "short_name" | "canonical_name">;
  size?: number;
  className?: string;
}) {
  const { bg, fg } = partyColor(party);
  const px = `${size}px`;
  return (
    <span
      className={`flex-shrink-0 grid place-items-center rounded-full font-extrabold select-none ${className}`}
      style={{
        width: px,
        height: px,
        background: bg,
        color: fg,
        fontSize: `${Math.round(size * 0.44)}px`,
      }}
      aria-hidden="true"
    >
      {initialOf(party)}
    </span>
  );
}
