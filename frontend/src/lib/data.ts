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
