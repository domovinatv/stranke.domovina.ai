import type { Funding, FundingParty, Party } from "@/lib/types";

/**
 * Raspored novca 11. saziva kao niz razdoblja s točnim granicama (ponoć po
 * zagrebačkom vremenu) i iznosom po primatelju. Iz toga se za bilo koji
 * trenutak t računa stopa (€/s) i kumulativ od 16. 5. 2024.
 *
 * Zakon isplaćuje tromjesečno u jednakim iznosima (čl. 10.), pa je linearna
 * akumulacija unutar razdoblja vizualizacija obračuna, a ne stvarnih uplata.
 */

export type SegmentSource = "odluka" | "zakon" | "procjena";

export interface Segment {
  label: string;
  start: number; // ms epoch, uključivo
  end: number; // ms epoch, isključivo
  source: SegmentSource;
  nn: string | null;
  amounts: Float64Array; // po primatelju, istim redom kao Schedule.parties
  total: number;
  /** Ponderirani mandati M + 1,1 × Ž za koje vrijedi iznos. */
  weight: number;
}

export interface Schedule {
  parties: FundingParty[];
  segments: Segment[];
  start: number;
  end: number;
  /** Iznos po primatelju za cijeli saziv (završena + odlučena + projekcija). */
  totals: Float64Array;
  total: number;
}

/** Zadnja nedjelja u mjesecu (0-based mjesec), dan u mjesecu. */
function lastSunday(y: number, m: number): number {
  const last = new Date(Date.UTC(y, m + 1, 0));
  return last.getUTCDate() - last.getUTCDay();
}

/**
 * Ponoć datuma `iso` (YYYY-MM-DD) po zagrebačkom vremenu, kao ms epoch.
 * Ljetno računanje vremena (CEST, +2) od zadnje nedjelje u ožujku do zadnje
 * nedjelje u listopadu; ponoć dana promjene je još u starom pomaku.
 */
export function zagrebMidnight(iso: string): number {
  const [y, mo, d] = iso.split("-").map(Number);
  const m = mo - 1;
  const ord = m * 100 + d;
  const dstFrom = 2 * 100 + lastSunday(y, 2); // ožujak
  const dstTo = 9 * 100 + lastSunday(y, 9); // listopad
  const dst = ord > dstFrom && ord <= dstTo;
  return Date.UTC(y, m, d) - (dst ? 2 : 1) * 3600_000;
}

function nextDay(iso: string): string {
  const t = new Date(iso + "T00:00:00Z");
  t.setUTCDate(t.getUTCDate() + 1);
  return t.toISOString().slice(0, 10);
}

export function buildSchedule(data: Funding): Schedule {
  const parties = [...data.parties].sort(
    (a, b) =>
      (data.projection.parties[b.name]?.saziv_total_eur ?? 0) -
      (data.projection.parties[a.name]?.saziv_total_eur ?? 0),
  );
  const n = parties.length;
  const segments: Segment[] = [];
  const lastRate = data.rates[data.rates.length - 1];
  const weightOf = (m: number, f: number) => m + 1.1 * f;

  // Razdoblja iz odluka Odbora (završena i ono koje je u tijeku).
  for (const p of data.periods) {
    const amounts = new Float64Array(n);
    parties.forEach((party, i) => (amounts[i] = party.by_period[p.label] ?? 0));
    const rate =
      data.rates.find((r) => r.nn === p.nn && r.period_from <= p.from && p.from <= r.period_to) ??
      data.rates.find((r) => r.nn === p.nn) ??
      lastRate;
    segments.push({
      label: p.label,
      start: zagrebMidnight(p.from),
      end: zagrebMidnight(nextDay(p.to)),
      source: "odluka",
      nn: p.nn,
      amounts,
      total: amounts.reduce((s, v) => s + v, 0),
      weight: weightOf(rate.mps_male, rate.mps_female),
    });
  }

  // Projekcija: godine za koje odluka još ne postoji, po tromjesečjima.
  const decidedEnd = segments[segments.length - 1].end;
  const endIso = data.projection.end;
  for (const y of data.projection.years) {
    const quarters: Array<{ from: string; to: string; share: number; label: string }> = [];
    const qs = [
      ["01-01", "03-31"],
      ["04-01", "06-30"],
      ["07-01", "09-30"],
      ["10-01", "12-31"],
    ];
    let left = y.quarters;
    qs.forEach(([a, b], qi) => {
      if (left <= 1e-9) return;
      const from = `${y.year}-${a}`;
      let to = `${y.year}-${b}`;
      const share = Math.min(1, left);
      if (share < 1) to = endIso; // razmjerni dio zadnjeg tromjesečja
      left -= share;
      const dm = (iso: string) => `${Number(iso.slice(8, 10))}.${Number(iso.slice(5, 7))}.`;
      const label = share < 1 ? `${dm(from)}–${dm(to)}${y.year}.` : `Q${qi + 1}/${y.year}`;
      quarters.push({ from, to, share, label });
    });
    for (const q of quarters) {
      const start = zagrebMidnight(q.from);
      if (start < decidedEnd) continue;
      const amounts = new Float64Array(n);
      parties.forEach((party, i) => {
        const yearAmt = data.projection.parties[party.name]?.by_year[String(y.year)] ?? 0;
        amounts[i] = (yearAmt * q.share) / y.quarters;
      });
      segments.push({
        label: q.label,
        start,
        end: zagrebMidnight(nextDay(q.to)),
        source: y.tax_kind === "ostvareno" ? "zakon" : "procjena",
        nn: null,
        amounts,
        total: amounts.reduce((s, v) => s + v, 0),
        weight: weightOf(lastRate.mps_male, lastRate.mps_female),
      });
    }
  }

  const totals = new Float64Array(n);
  for (const s of segments) for (let i = 0; i < n; i++) totals[i] += s.amounts[i];
  return {
    parties,
    segments,
    start: segments[0].start,
    end: segments[segments.length - 1].end,
    totals,
    total: totals.reduce((s, v) => s + v, 0),
  };
}

export function segmentAt(s: Schedule, t: number): Segment | null {
  for (const seg of s.segments) if (t >= seg.start && t < seg.end) return seg;
  return null;
}

/** Kumulativ od početka saziva do t; puni `out` po primatelju, vraća zbroj. */
export function cumulativeAt(s: Schedule, t: number, out: Float64Array): number {
  out.fill(0);
  let total = 0;
  for (const seg of s.segments) {
    if (t <= seg.start) break;
    const f = t >= seg.end ? 1 : (t - seg.start) / (seg.end - seg.start);
    for (let i = 0; i < out.length; i++) out[i] += seg.amounts[i] * f;
    total += seg.total * f;
  }
  return total;
}

/** € u sekundi u razdoblju `seg` (ukupno ili za primatelja i). */
export const perSecond = (seg: Segment, amount: number) => amount / ((seg.end - seg.start) / 1000);

export function catalogAvatar(p: FundingParty, catalog: Map<string, Party>) {
  const cat = p.slug ? catalog.get(p.slug) : undefined;
  return {
    slug: p.slug ?? p.name,
    canonical_name: p.name,
    short_name: cat?.short_name ?? p.short ?? undefined,
    logo: cat?.logo,
    logo_sizes: cat?.logo_sizes,
    brand_color: cat?.brand_color,
  };
}

/** Ostali prihodi iz revizije DUR-a, u eurima godišnje. */
export const OTHER_KEYS = [
  { key: "local", label: "lokalni proračuni", note: "županije, gradovi, općine; i to je javni novac" },
  { key: "members", label: "članarine", note: null },
  { key: "donations", label: "donacije", note: null },
  { key: "other", label: "ostali prihodi", note: "kamate, najam, prodaja i sl." },
] as const;
export type OtherKey = (typeof OTHER_KEYS)[number]["key"];

export interface OtherIncome {
  year: number;
  /** €/s po izvoru, za sve stranke zajedno. */
  bySource: Record<OtherKey, number>;
  /** €/s po stranci, istim redom kao Schedule.parties (NaN = nema revizije). */
  byParty: Float64Array;
  /** €/s po stranci i izvoru (0 kad nema revizije). */
  byPartySource: Record<OtherKey, Float64Array>;
  rate: number;
  covered: number;
}

/**
 * Ostale prihode (sve osim državnog proračuna) uzima iz zadnje revizije DUR-a
 * i pretpostavlja da teku istom brzinom kao te godine.
 */
export function buildOther(data: Funding, s: Schedule): OtherIncome | null {
  const audits = data.audits?.parties ?? [];
  const bySlug = new Map(audits.filter((a) => a.slug).map((a) => [a.slug!, a]));
  const years = audits.flatMap((a) => Object.keys(a.years).map(Number));
  if (!years.length) return null;
  const year = Math.max(...years);
  const secs = (Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1)) / 1000;
  const bySource = { local: 0, members: 0, donations: 0, other: 0 } as Record<OtherKey, number>;
  const byParty = new Float64Array(s.parties.length).fill(NaN);
  const byPartySource = Object.fromEntries(
    OTHER_KEYS.map(({ key }) => [key, new Float64Array(s.parties.length)]),
  ) as Record<OtherKey, Float64Array>;
  let covered = 0;
  s.parties.forEach((p, i) => {
    const y = p.slug ? bySlug.get(p.slug)?.years[String(year)] : undefined;
    if (!y || y.currency !== "EUR") return;
    covered++;
    let sum = 0;
    for (const { key } of OTHER_KEYS) {
      const v = (y.revenue[key] ?? 0) / secs;
      bySource[key] += v;
      byPartySource[key][i] = v;
      sum += v;
    }
    byParty[i] = sum;
  });
  const rate = OTHER_KEYS.reduce((a, { key }) => a + bySource[key], 0);
  return { year, bySource, byParty, byPartySource, rate, covered };
}


/** Adresa zasebnog ekrana primatelja; nezavisni zastupnici nemaju slug stranke. */
export function liveSlug(p: FundingParty): string {
  return (
    p.slug ??
    p.name
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
  );
}

/** Udio javnog novca (državni + lokalni proračuni) u stopi primatelja i. */
export function publicShare(seg: Segment | null, other: OtherIncome | null, i: number) {
  const state = seg ? perSecond(seg, seg.amounts[i]) : 0;
  if (!other || Number.isNaN(other.byParty[i])) return null;
  const pub = state + other.byPartySource.local[i];
  const all = state + other.byParty[i];
  return all > 0 ? { state, local: other.byPartySource.local[i], pub, priv: all - pub, all, share: pub / all } : null;
}
