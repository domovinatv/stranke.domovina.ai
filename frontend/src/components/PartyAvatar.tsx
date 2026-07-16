import { useState } from "react";
import type { Party } from "@/lib/types";
import { logoSrc, logoSrcSet } from "@/lib/data";

/**
 * Logo stranke unutar fiksnog kvadratnog *footprinta* (redci ostaju poravnati)
 * ali bez vidljivog okvira: ne-kvadratni logotipi zadržavaju omjer i samo
 * zauzimaju manje širine/visine — nikad izrezani, nikad letterboxani.
 *
 * Fallback lanac: logo s CDN-a → (nema loga ili img error) → inicijal-avatar.
 * Inicijal-avatar koristi službenu brand_color kad postoji, inače pozadinu
 * deterministički izvedenu iz canonical_name — ista stranka uvijek ista boja.
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

const HEX_COLOR_RE = /^#[0-9a-f]{6}$/i;

/** Light or dark text over an arbitrary background, by YIQ perceived brightness. */
function contrastFg(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 0xff;
  const g = (n >> 8) & 0xff;
  const b = n & 0xff;
  const yiq = (r * 299 + g * 587 + b * 114) / 1000;
  return yiq >= 150 ? "#1E293B" : "#FFFFFF";
}

export function partyColor(
  party: Pick<Party, "canonical_name" | "brand_color">,
): { bg: string; fg: string } {
  if (party.brand_color && HEX_COLOR_RE.test(party.brand_color)) {
    return { bg: party.brand_color, fg: contrastFg(party.brand_color) };
  }
  return PALETTE[hashString(party.canonical_name || "") % PALETTE.length];
}

type AvatarParty = Pick<
  Party,
  "slug" | "short_name" | "canonical_name" | "logo" | "logo_sizes" | "brand_color"
>;

export function PartyAvatar({
  party,
  size = 48,
  className = "",
}: {
  party: AvatarParty;
  size?: number;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const src = logoSrc(party);
  const px = `${size}px`;

  if (src && !failed) {
    return (
      <span
        className={`flex-shrink-0 grid place-items-center ${className}`}
        style={{ width: px, height: px }}
      >
        <img
          src={src}
          srcSet={logoSrcSet(party)}
          sizes={px}
          alt={party.canonical_name}
          loading="lazy"
          decoding="async"
          className="max-w-full max-h-full w-auto h-auto object-contain"
          onError={() => setFailed(true)}
        />
      </span>
    );
  }

  const { bg, fg } = partyColor(party);
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
