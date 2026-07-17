import type { City, Party, PartyDetail, Stats } from "./types";

const memo = new Map<string, Promise<unknown>>();

function fetchJson<T>(url: string): Promise<T> {
  const cached = memo.get(url) as Promise<T> | undefined;
  if (cached) return cached;
  const p = fetch(url, { credentials: "omit" }).then((r) => {
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json() as Promise<T>;
  });
  memo.set(url, p);
  return p;
}

export const loadParties = () => fetchJson<Party[]>("/data/parties.json");
export const loadCities = () => fetchJson<City[]>("/data/cities.json");
export const loadStats = () => fetchJson<Stats>("/data/stats.json");
export const loadPartyDetail = (slug: string) =>
  fetchJson<PartyDetail>(`/data/parties/${slug}.json`);

const DIACRITIC_RE = /[\u0300-\u036f]/g;

export function deburr(s: string): string {
  return s.normalize("NFKD").replace(DIACRITIC_RE, "").toLowerCase();
}

/** "2019-02-14" → "14. 2. 2019." (hr-HR), falls back to raw string. */
export function formatDate(iso?: string | null): string | null {
  if (!iso) return null;
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return iso;
  return `${Number(m[3])}. ${Number(m[2])}. ${m[1]}.`;
}

export function yearOf(iso?: string | null): string | null {
  if (!iso) return null;
  const m = iso.match(/^(\d{4})/);
  return m ? m[1] : null;
}

export function googleMapsUrl(p: Pick<Party, "lat" | "lng">): string | null {
  if (p.lat == null || p.lng == null) return null;
  return `https://www.google.com/maps?q=${p.lat},${p.lng}`;
}

/**
 * Demo novčanik stranke — politika/novcanik-prototip serviran kroz ff-edge
 * dispatcher na `*.ff.hr` (svih 155 AKTIVNIH iz ovog kataloga). Kratki
 * `wallet_alias` (hdz.ff.hr, sdp.ff.hr…) izveden je iz VLASTITE <label>.hr
 * domene stranke (src/wallet_alias.py); ostale idu punim slugom. Ugašene
 * (PRESTANAK) se NE izlažu — nisu u worker katalogu pa bi pale na whitelabel.
 */
export function walletUrl(p: Pick<Party, "slug" | "status" | "wallet_alias">): string | null {
  if (p.status !== "AKTIVAN") return null;
  return `https://${p.wallet_alias ?? p.slug}.ff.hr`;
}

export const LOGO_CDN = "https://p.ff.hr";

/** Web-default logo (≤512px PNG) or null when the party has none. */
export function logoSrc(party: Pick<Party, "logo">): string | null {
  if (!party.logo) return null;
  return `${LOGO_CDN}/logos/${party.logo}`;
}

/**
 * srcset over the CDN size ladder (192/256/512/1024). Tiers exist only where
 * the source image honestly fills them, so the browser picks the best real
 * resolution for the rendered size × devicePixelRatio and never upscales a
 * tiny logo into a blurry big one.
 */
export function logoSrcSet(
  party: Pick<Party, "logo" | "slug" | "logo_sizes">,
): string | undefined {
  if (!party.logo || !party.logo_sizes?.length) return undefined;
  return party.logo_sizes
    .map((s) => `${LOGO_CDN}/logos/${s}/${party.slug}.png ${s}w`)
    .join(", ");
}
