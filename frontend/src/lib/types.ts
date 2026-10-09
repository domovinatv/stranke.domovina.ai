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
  currency?: "HRK" | "EUR";
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
  /** Null when the last decision covers only part of a year. */
  year_eur: number | null;
  total_eur: number;
  by_period: Record<string, number>;
  /** Seated MPs who are still members today (11th convocation only). */
  seated_male?: number;
  seated_female?: number;
}

export interface FundingProjectionYear {
  year: number;
  tax_year: number;
  tax_revenue_eur: number;
  tax_kind: "ostvareno" | "plan" | "projekcija";
  tax_source: string | null;
  annual_eur: number;
  quarters: number;
  amount_eur: number;
  month_m: number;
  month_f: number;
  alt: { tax_revenue_eur: number; growth: number; amount_eur: number } | null;
}

export interface FundingProjection {
  end: string;
  open_periods: string[];
  years: FundingProjectionYear[];
  parties: Record<string, {
    open_eur: number;
    by_year: Record<string, number>;
    projected_eur: number;
    saziv_total_eur: number;
    saziv_total_alt_eur: number;
  }>;
  projected_eur: number;
  saziv_total_eur: number;
  saziv_total_alt_eur: number;
  h1: { year: number; growth: number; status: string; source_url: string } | null;
  assumptions: string[];
}

export interface FundingConvocation {
  id: number;
  label: string;
  start: string;
  end: string;
  periods: FundingPeriod[];
  parties: FundingParty[];
  rates: FundingRate[];
  received_eur: number;
  mps_male: number;
  mps_female: number;
}

export interface TaxYear {
  year: number;
  kind: "ostvareno" | "plan" | "projekcija";
  tax_revenue_eur: number;
  source_url: string;
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
  projection: FundingProjection;
  previous: FundingConvocation;
  taxes: TaxYear[];
  reports: { year: number; page_url: string; pdf_url: string; currency: "HRK" | "EUR"; allocated_eur: number; paid_eur: number }[];
  checks: { rows: number; max_diff: number; split_2024_max_diff: number };
  seated_fetched_at: string;
}
