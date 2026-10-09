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

export interface FundingRate {
  nn: string;
  url: string;
  adopted: string;
  in_force: string;
  period_from: string;
  period_to: string;
  annual_budget_eur: number;
  quarter_total_eur: number;
  mps_male: number;
  mps_female: number;
  quarter_m: number;
  quarter_f: number;
  month_m: number;
  month_f: number;
}

export interface FundingPeriod {
  label: string;
  from: string;
  to: string;
  nn: string;
  /** Quarter ended by `as_of` → counted in "received so far". */
  ended: boolean;
}

export interface FundingParty {
  name: string;
  slug: string | null;
  short: string | null;
  /** National-minority MP funded personally as "nezavisni zastupnik". */
  independent: boolean;
  /** Mandates the current decision funds (by final election results). */
  mps_male: number;
  mps_female: number;
  month_eur: number;
  year_eur: number;
  total_eur: number;
  by_period: Record<string, number>;
  /** Seated MPs who are still members today. */
  seated_male: number;
  seated_female: number;
}

export interface FundingMp {
  name: string;
  gender: "M" | "F";
  party: string;
  party_full: string | null;
  club: string;
  elected_on: string | null;
  constituency: string | null;
  mandate_start: string | null;
  minority: boolean;
  img: string | null;
  profile: string;
  /** Recipient in the current decision, null when the MP left the party holding the mandate. */
  recipient: string | null;
  /** "switched": left the party holding the mandate; "substitute": minority substitute, decision names the predecessor. */
  recipient_note: "switched" | "substitute" | null;
  mandate_changes: string | null;
  seat_month_eur: number;
}

export interface Funding {
  generated_at: string;
  as_of: string;
  year: string;
  convocation_start: string;
  totals: {
    received_eur: number;
    year_eur: number;
    month_eur: number;
    mps_male: number;
    mps_female: number;
    seated: number;
    seated_female: number;
  };
  rates: FundingRate[];
  periods: FundingPeriod[];
  parties: FundingParty[];
  mps: FundingMp[];
  reports: { year: number; page_url: string; pdf_url: string; allocated_eur: number; paid_eur: number }[];
  seated_fetched_at: string;
}
