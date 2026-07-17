export type PartyStatus = "AKTIVAN" | "PRESTANAK";

export interface Party {
  id: number;
  slug: string;
  canonical_name: string;
  short_name?: string;
  oib?: string;
  reg_number?: string;
  /** Missing for a couple of manually-added rows → "unknown" in the UI. */
  status?: PartyStatus;
  registered_at?: string;
  status_date?: string;
  city?: string;
  address?: string;
  county?: string;
  founded_place?: string;
  founded_date?: string;
  website?: string;
  email?: string;
  phone?: string;
  phone_kind?: "mobile" | "landline" | "other";
  phone_e164?: string;
  fb_url?: string;
  ig_url?: string;
  x_url?: string;
  president?: string;
  wiki_url?: string;
  /** Kratki wallet subdomain ({wallet_alias}.ff.hr) — iz vlastite <label>.hr domene stranke. */
  wallet_alias?: string;
  lat?: number;
  lng?: number;
  /** CDN logo filename, e.g. "hrvatska-demokratska-zajednica.png" → https://p.ff.hr/logos/{logo}. */
  logo?: string;
  /** Available density-ladder tiers (subset of [192, 256, 512, 1024]) at https://p.ff.hr/logos/{size}/{slug}.png. */
  logo_sizes?: number[];
  /** Official/derived party brand color as "#RRGGBB". */
  brand_color?: string;
}

export interface City {
  name: string;
  n: number;
  active: number;
}

export interface GlobalStats {
  total: number;
  active: number;
  defunct: number;
  with_geo: number;
  can_sms: number;
  can_call: number;
  can_email: number;
  can_mail: number;
  can_web: number;
  full_contact: number;
  with_president: number;
  with_oib: number;
  with_wiki: number;
}

export interface Stats {
  global: GlobalStats;
  decades: Array<{ decade: string; n: number }>;
}

export interface PartyPerson {
  full_name: string;
  role?: string;
  represents?: number;
}

export interface PartyFunction {
  function: string;
  holder: string;
  mandate_start?: string | null;
  mandate_end?: string | null;
}

export interface PartyDetail {
  id: number;
  slug: string;
  notes?: string;
  seat?: string;
  book_number?: number;
  people: PartyPerson[];
  functions: PartyFunction[];
  aliases: Array<{ alias: string; source?: string }>;
}
