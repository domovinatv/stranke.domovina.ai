import { ChevronDown, ChevronRight, Euro, ExternalLink, Search } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { deburr, formatDate, loadFunding, loadParties } from "@/lib/data";
import type { Funding, FundingMp, FundingParty, Party } from "@/lib/types";
import { PageSpinner } from "@/components/PageSpinner";
import { PartyAvatar } from "@/components/PartyAvatar";
import { buildSchedule, catalogAvatar, perSecond, segmentAt } from "@/lib/fundingLive";

const MALE = "#002F6C";
const FEMALE = "#DB2777";

const eur = (n: number, digits = 2) =>
  n.toLocaleString("hr-HR", { minimumFractionDigits: digits, maximumFractionDigits: digits }) + " €";

const mil = (n: number) =>
  (n / 1e6).toLocaleString("hr-HR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " mil. €";

const pct = (a: number, b: number) =>
  ((100 * a) / b).toLocaleString("hr-HR", { maximumFractionDigits: 1 }) + " %";

export default function FundingRoute() {
  const [data, setData] = useState<Funding | null>(null);
  const [catalog, setCatalog] = useState<Map<string, Party>>(new Map());

  useEffect(() => {
    document.title = "Koliko stranke dobivaju iz proračuna · DOMOVINA Stranke";
    loadFunding().then(setData);
    loadParties()
      .then((ps) => setCatalog(new Map(ps.map((p) => [p.slug, p]))))
      .catch(() => undefined);
  }, []);

  if (!data) return <PageSpinner />;
  const cur = data.rates[data.rates.length - 1];
  const t = data.totals;

  return (
    <section className="container-page py-6 sm:py-10">
      <header className="mb-8">
        <div className="pill mb-2 inline-flex items-center gap-1.5">
          <Euro size={13} /> 11. saziv Hrvatskoga sabora
        </div>
        <h1 className="text-2xl sm:text-4xl font-extrabold text-navy max-w-3xl leading-tight">
          Koliko stranke dobivaju iz državnog proračuna
        </h1>
        <p className="text-muted mt-3 max-w-2xl leading-relaxed">
          Svaki saborski mandat stranci donosi jednak iznos, a mandat
          zastupnice 10 % više jer su žene u Saboru podzastupljene. Iznosi su
          preuzeti iz odluka Odbora za Ustav, Poslovnik i politički sustav
          objavljenih u Narodnim novinama i provjereni prema Saborovu
          godišnjem izvješću o isplatama.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          label={`Raspoređeno od ${formatDate(data.convocation_start)}`}
          value={mil(t.received_eur)}
          note={`zaključno s ${formatDate(data.as_of)}`}
          accent
        />
        <Kpi label="Po zastupniku mjesečno" value={eur(cur.month_m)} note={`u ${data.year}.`} color={MALE} />
        <Kpi
          label="Po zastupnici mjesečno"
          value={eur(cur.month_f)}
          note="+10 % za podzastupljeni spol"
          color={FEMALE}
        />
        <Kpi
          label={`Ukupno za ${data.year}.`}
          value={mil(t.year_eur)}
          note={`${eur(t.month_eur, 0)} mjesečno svim strankama`}
        />
      </div>

      <Link
        to="/financiranje/uzivo"
        className="card card-hover mt-3 flex items-center gap-3 p-4 no-underline"
      >
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          <span className="absolute inline-flex h-full w-full rounded-full bg-flag-red opacity-60 motion-safe:animate-ping" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-flag-red" />
        </span>
        <span className="flex-1 text-sm text-navy-700">
          <strong className="text-navy">Uživo:</strong> svake sekunde strankama
          pripada ≈ {liveRate(data)} €.
          Pogledajte kako brojači rastu dok gledate.
        </span>
        <ChevronRight size={18} className="text-muted shrink-0" />
      </Link>

      <Formula data={data} />

      <h2 className="mt-12 mb-1 text-xl font-bold text-navy">Po strankama</h2>
      <p className="text-sm text-muted mb-4 max-w-3xl">
        Broj mandata je onaj za koji stranka prima novac prema odluci{" "}
        <a href={cur.url} target="_blank" rel="noopener">NN {cur.nn}</a>, dakle
        prema konačnim rezultatima izbora, a ne prema tome tko danas sjedi u
        klupama. Kliknite redak za razradu po tromjesečjima i zastupnicima.
      </p>
      <PartyTable data={data} catalog={catalog} />

      <Projection data={data} catalog={catalog} />

      <h2 className="mt-12 mb-1 text-xl font-bold text-navy">Po osobi</h2>
      <p className="text-sm text-muted mb-4 max-w-3xl">
        Koliko mjesečno donosi mandat svakog od {t.seated} zastupnika koji
        danas sjede u Saboru i kojoj stranci taj novac ide. Kad je zastupnik
        napustio stranku s čije je liste izabran, novac i dalje ide toj stranci
        (čl. 7. Zakona), a ne njemu ni njegovoj novoj stranci.
      </p>
      <MpList data={data} />

      <Previous data={data} catalog={catalog} />

      <h2 className="mt-12 mb-1 text-xl font-bold text-navy">Kako se iznos mijenjao, 2020.–2028.</h2>
      <p className="text-sm text-muted mb-4 max-w-3xl">
        Iznos po mandatu raste jer se računa od poreznih prihoda iz godine
        N−2. Unutar godine se mijenja samo kad se promijeni omjer muškaraca
        i žena (npr. kad zastupnika zamijeni zamjenica), jer se isti iznos
        tada dijeli drugačije. Iznosi do 2022. preračunati su iz kuna
        (7,53450 kn/€).
      </p>
      <RatesTable data={data} />

      <h3 className="mt-8 mb-1 text-lg font-bold text-navy">Porezi, cijene i gospodarstvo</h3>
      <p className="text-sm text-muted mb-4 max-w-3xl">
        Novac za stranke je 0,075 % poreznih prihoda državnog proračuna
        (skupina računa 61) iz godine N−2, pa raste točno onoliko koliko
        su porasli porezni prihodi. Zakon ga ne veže ni uz inflaciju ni uz
        BDP; usporedba pokazuje kako se ti prihodi kreću u odnosu na cijene i
        gospodarstvo.
      </p>
      <MacroSummary data={data} />
      <TaxTable data={data} />
      {data.macro && (
        <p className="text-xs text-muted mt-2 max-w-3xl">
          Inflacija: HICP, prosječna godišnja stopa (
          <a href={data.macro.sources.hicp_pct.page} target="_blank" rel="noopener">Eurostat prc_hicp_aind</a>
          ), a ne nacionalni CPI DZS-a. BDP: Eurostat{" "}
          <a href={data.macro.sources.gdp_real_pct.page} target="_blank" rel="noopener">nama_10_gdp</a>
          , zadnje godine su privremene. Porezi / BDP: porezni prihodi
          državnog proračuna (bez doprinosa i bez lokalne razine) u nominalnom
          BDP-u. Od 2024. porez na dohodak više nije prihod državnog
          proračuna, pa ta godina nije izravno usporediva s ranijima.
          Preuzeto {formatDate(data.macro.retrieved)}.
        </p>
      )}

      <Sources data={data} />
    </section>
  );
}

function liveRate(data: Funding) {
  const s = buildSchedule(data);
  const seg = segmentAt(s, Date.now()) ?? s.segments[s.segments.length - 1];
  return perSecond(seg, seg.total).toLocaleString("hr-HR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function Kpi({
  label,
  value,
  note,
  accent,
  color,
}: {
  label: string;
  value: string;
  note?: string;
  accent?: boolean;
  color?: string;
}) {
  return (
    <div className="card p-4">
      <div className="field-label">{label}</div>
      <div
        className={`text-2xl sm:text-3xl font-extrabold tabular-nums ${accent ? "text-flag-red" : "text-navy"}`}
        style={color ? { color } : undefined}
      >
        {value}
      </div>
      {note && <div className="text-xs text-muted mt-1">{note}</div>}
    </div>
  );
}

function Formula({ data }: { data: Funding }) {
  const r = data.rates[data.rates.length - 1];
  const weighted = r.mps_male + 1.1 * r.mps_female;
  return (
    <div className="card p-5 mt-6">
      <div className="field-label">Kako se računa ({data.year}.)</div>
      <ol className="grid gap-4 sm:grid-cols-3 text-sm text-navy-700 mt-2">
        <li>
          <div className="text-lg font-bold text-navy tabular-nums">{mil(r.annual_budget_eur)}</div>
          0,075 % ostvarenih poreznih prihoda iz posljednjeg objavljenog
          godišnjeg izvještaja o izvršenju proračuna (čl. 5.), isplaćuje se
          tromjesečno: {eur(r.quarter_total_eur)} po tromjesečju.
        </li>
        <li>
          <div className="text-lg font-bold text-navy tabular-nums">
            {r.mps_male} + 1,1 × {r.mps_female} ={" "}
            {weighted.toLocaleString("hr-HR", { maximumFractionDigits: 1 })}
          </div>
          Mandati: {r.mps_male} muškaraca i {r.mps_female} žena. Žena je{" "}
          {pct(r.mps_female, r.mps_male + r.mps_female)}, manje od 40 %, pa
          svaka zastupnica vrijedi 1,1 mandata (čl. 9.).
        </li>
        <li>
          <div className="text-lg font-bold tabular-nums">
            <span style={{ color: MALE }}>{eur(r.quarter_m)}</span>
            <span className="text-muted font-normal"> / </span>
            <span style={{ color: FEMALE }}>{eur(r.quarter_f)}</span>
          </div>
          Tromjesečni iznos po zastupniku i zastupnici, odnosno{" "}
          {eur(r.month_m)} i {eur(r.month_f)} mjesečno. Novac ide stranci koja
          je predložila listu (čl. 7.).
        </li>
      </ol>
    </div>
  );
}

function GenderBar({ m, f, max }: { m: number; f: number; max: number }) {
  return (
    <div className="flex h-2.5 w-full max-w-40 rounded-full bg-surface overflow-hidden" aria-hidden="true">
      <div style={{ width: `${(100 * m) / max}%`, background: MALE }} />
      <div style={{ width: `${(100 * f) / max}%`, background: FEMALE }} />
    </div>
  );
}

function PartyTable({ data, catalog }: { data: Funding; catalog: Map<string, Party> }) {
  const [open, setOpen] = useState<string | null>(null);
  const max = Math.max(...data.parties.map((p) => p.mps_male + p.mps_female));
  const t = data.totals;

  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-muted border-b border-border">
            <th className="p-3 font-semibold">Primatelj</th>
            <th className="p-3 font-semibold">Mandati M / Ž</th>
            <th className="p-3 font-semibold text-right">Mjesečno</th>
            <th className="p-3 font-semibold text-right hidden md:table-cell">{data.year}.</th>
            <th className="p-3 font-semibold text-right">Ukupno 11. saziv</th>
            <th className="p-3 w-8" />
          </tr>
        </thead>
        <tbody>
          {data.parties.map((p) => {
            const isOpen = open === p.name;
            const cat = p.slug ? catalog.get(p.slug) : undefined;
            return (
              <Fragment key={p.name}>
                <tr
                  className={`border-b border-border/70 cursor-pointer hover:bg-surface/60 ${isOpen ? "bg-surface/60" : ""}`}
                  onClick={() => setOpen(isOpen ? null : p.name)}
                >
                  <td className="p-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <PartyAvatar
                        size={32}
                        party={{
                          slug: p.slug ?? p.name,
                          canonical_name: p.name,
                          short_name: cat?.short_name ?? p.short ?? undefined,
                          logo: cat?.logo,
                          logo_sizes: cat?.logo_sizes,
                          brand_color: cat?.brand_color,
                        }}
                      />
                      <div className="min-w-0">
                        <div className="font-semibold text-navy leading-snug">{p.name}</div>
                        {p.independent && (
                          <div className="text-xs text-muted">zastupnik nacionalne manjine · nezavisni zastupnik</div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="p-3">
                    <div className="tabular-nums whitespace-nowrap mb-1">
                      <span style={{ color: MALE }} className="font-semibold">{p.mps_male}</span>
                      <span className="text-muted"> / </span>
                      <span style={{ color: FEMALE }} className="font-semibold">{p.mps_female}</span>
                    </div>
                    <GenderBar m={p.mps_male} f={p.mps_female} max={max} />
                  </td>
                  <td className="p-3 text-right tabular-nums whitespace-nowrap">{eur(p.month_eur)}</td>
                  <td className="p-3 text-right tabular-nums whitespace-nowrap hidden md:table-cell">{p.year_eur != null ? eur(p.year_eur) : "–"}</td>
                  <td className="p-3 text-right tabular-nums whitespace-nowrap font-bold text-navy">{eur(p.total_eur)}</td>
                  <td className="p-3 text-muted">
                    <ChevronDown size={16} className={`transition-transform ${isOpen ? "rotate-180" : ""}`} />
                  </td>
                </tr>
                {isOpen && (
                  <tr className="border-b border-border bg-surface/40">
                    <td colSpan={6} className="p-4">
                      <PartyDetail data={data} party={p} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="font-bold text-navy">
            <td className="p-3">Ukupno</td>
            <td className="p-3 tabular-nums">
              <span style={{ color: MALE }}>{t.mps_male}</span>
              <span className="text-muted font-normal"> / </span>
              <span style={{ color: FEMALE }}>{t.mps_female}</span>
            </td>
            <td className="p-3 text-right tabular-nums whitespace-nowrap">{eur(t.month_eur)}</td>
            <td className="p-3 text-right tabular-nums whitespace-nowrap hidden md:table-cell">{eur(t.year_eur)}</td>
            <td className="p-3 text-right tabular-nums whitespace-nowrap text-flag-red">{eur(t.received_eur)}</td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function PartyDetail({ data, party }: { data: Funding; party: FundingParty }) {
  const members = data.mps.filter((m) => m.recipient === party.name);
  const funded = party.mps_male + party.mps_female;
  const gap = funded - members.length;
  const max = Math.max(...data.periods.map((p) => party.by_period[p.label] ?? 0), 1);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div>
        <div className="field-label">Po tromjesečjima</div>
        <ul className="space-y-1">
          {data.periods.map((per) => {
            const v = party.by_period[per.label] ?? 0;
            return (
              <li key={per.label} className="grid grid-cols-[6.5rem_1fr_auto] items-center gap-2 text-xs">
                <span className="text-muted tabular-nums">{per.label}</span>
                <span className="h-2 rounded-full bg-white overflow-hidden">
                  <span
                    className="block h-full"
                    style={{ width: `${(100 * v) / max}%`, background: per.ended ? MALE : "#A6BDDB" }}
                  />
                </span>
                <span className={`tabular-nums text-right ${per.ended ? "text-navy" : "text-muted"}`}>
                  {eur(v)}
                  {!per.ended && " · u tijeku"}
                </span>
              </li>
            );
          })}
        </ul>
        <p className="text-xs text-muted mt-2">
          Prvo razdoblje je razmjerno danima od konstituiranja Sabora (16. 5. 2024.).
          Tromjesečje u tijeku nije uračunato u ukupni zbroj.
        </p>
      </div>
      <div>
        <div className="field-label">
          {party.independent ? "Zastupnik" : `Članovi u klupama (${members.length} od ${funded} financiranih mandata)`}
        </div>
        {members.length > 0 ? (
          <ul className="grid sm:grid-cols-2 gap-x-4 gap-y-1">
            {members.map((m) => (
              <li key={m.name} className="flex items-center justify-between gap-2 text-sm">
                <a href={m.profile} target="_blank" rel="noopener" className="truncate">
                  <GenderDot g={m.gender} /> {m.name}
                </a>
                <span className="tabular-nums text-muted text-xs whitespace-nowrap">{eur(m.seat_month_eur)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Nijedan današnji zastupnik nije član ove stranke.</p>
        )}
        {gap > 0 && !party.independent && (
          <p className="text-xs text-muted mt-3">
            Stranka prima novac za {funded} mandata, a u Saboru danas sjedi {members.length}{" "}
            njezinih članova. Razliku čine zastupnici izabrani s njezine liste
            koji su u međuvremenu izašli iz stranke; novac za njihove mandate i
            dalje ide ovoj stranci.
          </p>
        )}
        {party.slug && (
          <Link to={`/stranka/${party.slug}`} className="inline-block text-sm mt-3 font-medium">
            Profil stranke →
          </Link>
        )}
      </div>
    </div>
  );
}

function GenderDot({ g }: { g: "M" | "F" }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full mr-1 align-middle"
      style={{ background: g === "F" ? FEMALE : MALE }}
      title={g === "F" ? "zastupnica" : "zastupnik"}
    />
  );
}

type Sort = "name" | "party" | "amount";

const PREVIEW = 20;

function MpList({ data }: { data: Funding }) {
  const [q, setQ] = useState("");
  const [gender, setGender] = useState<"" | "M" | "F">("");
  const [sort, setSort] = useState<Sort>("party");
  const [all, setAll] = useState(false);

  const rows = useMemo(() => {
    const needle = deburr(q.trim());
    const filtered = data.mps.filter(
      (m) =>
        (!gender || m.gender === gender) &&
        (!needle ||
          deburr(`${m.name} ${m.party} ${m.party_full ?? ""} ${m.recipient ?? ""}`).includes(needle)),
    );
    const byName = (a: FundingMp, b: FundingMp) => a.name.localeCompare(b.name, "hr");
    return filtered.sort((a, b) => {
      if (sort === "amount") return b.seat_month_eur - a.seat_month_eur || byName(a, b);
      if (sort === "party") {
        // Seats that no longer match the member's party go last.
        if (!a.recipient !== !b.recipient) return a.recipient ? -1 : 1;
        const ta = data.parties.findIndex((p) => p.name === a.recipient);
        const tb = data.parties.findIndex((p) => p.name === b.recipient);
        if (ta !== tb) return ta - tb;
      }
      return byName(a, b);
    });
  }, [data.mps, data.parties, q, gender, sort]);

  return (
    <div className="card">
      <div className="flex flex-wrap items-center gap-2 p-3 border-b border-border">
        <label className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            className="input pl-9"
            placeholder="Ime, stranka…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <select className="input w-auto" value={gender} onChange={(e) => setGender(e.target.value as "" | "M" | "F")}>
          <option value="">Svi</option>
          <option value="F">Zastupnice</option>
          <option value="M">Zastupnici</option>
        </select>
        <select className="input w-auto" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="party">Po primatelju</option>
          <option value="name">Po imenu</option>
          <option value="amount">Po iznosu</option>
        </select>
        <span className="text-xs text-muted tabular-nums">{rows.length} / {data.mps.length}</span>
      </div>
      <ul className="grid lg:grid-cols-2 lg:gap-x-6 px-0 lg:px-3">
        {(all || q ? rows : rows.slice(0, PREVIEW)).map((m) => (
          <li key={m.profile} className="flex items-start gap-3 p-3 lg:px-0 border-b border-border/70">
            {m.img ? (
              <img
                src={m.img}
                alt=""
                referrerPolicy="no-referrer"
                className="w-10 h-10 rounded-full object-cover object-top flex-shrink-0 bg-surface"
              />
            ) : (
              <span className="w-10 h-10 rounded-full bg-surface flex-shrink-0" />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <a href={m.profile} target="_blank" rel="noopener" className="font-semibold">
                  {m.name}
                </a>
                <span className="text-xs text-muted">{m.party}</span>
                {m.minority && <span className="pill !py-0">manjine</span>}
              </div>
              <div className="text-xs mt-0.5">
                {m.recipient_note === "substitute" ? (
                  <span className="text-navy-700" title={m.mandate_changes ?? undefined}>
                    Zamjena za zastupnika <strong>{m.recipient}</strong>; odluka sredstva vodi na njegovo ime.
                  </span>
                ) : m.recipient ? (
                  <span className="text-navy-700">Novac ide: <strong>{m.recipient}</strong></span>
                ) : (
                  <span className="text-amber-700">
                    Nije više u stranci s čije je liste izabran(a). Novac ide stranci predlagateljici liste.
                  </span>
                )}
              </div>
              {m.elected_on && (
                <div className="text-xs text-muted mt-0.5 line-clamp-1" title={m.elected_on}>
                  Izabran{m.gender === "F" ? "a" : ""}: {m.elected_on}
                  {m.mandate_start && m.mandate_start !== "16.05.2024" && ` · u Saboru od ${m.mandate_start}.`}
                </div>
              )}
            </div>
            <div className="text-right flex-shrink-0">
              <div
                className="font-bold tabular-nums whitespace-nowrap"
                style={{ color: m.gender === "F" ? FEMALE : MALE }}
              >
                {eur(m.seat_month_eur)}
              </div>
              <div className="text-[11px] text-muted">mjesečno</div>
            </div>
          </li>
        ))}
      </ul>
      {!all && !q && rows.length > PREVIEW && (
        <div className="p-3 text-center">
          <button type="button" className="btn-ghost" onClick={() => setAll(true)}>
            Prikaži sve ({rows.length})
          </button>
        </div>
      )}
    </div>
  );
}

interface RateRow {
  key: string;
  nn: string | null;
  url: string | null;
  from: string;
  to: string;
  mps: string;
  month_m: number;
  month_f: number;
  annual: number;
  tag?: string;
}

function rateRows(data: Funding): RateRow[] {
  const decided: RateRow[] = [...data.previous.rates, ...data.rates].map((r) => ({
    key: r.nn,
    nn: r.nn,
    url: r.url,
    from: r.period_from,
    to: r.period_to,
    mps: `${r.mps_male} / ${r.mps_female}`,
    month_m: r.month_m,
    month_f: r.month_f,
    annual: r.annual_budget_eur,
    tag: r.currency === "HRK" ? "kn → €" : undefined,
  }));
  const projected: RateRow[] = data.projection.years.map((y) => ({
    key: `p${y.year}`,
    nn: null,
    url: y.tax_source,
    from: `${y.year}-01-01`,
    to: y.year === Number(data.projection.end.slice(0, 4)) ? data.projection.end : `${y.year}-12-31`,
    mps: `${data.totals.mps_male} / ${data.totals.mps_female}`,
    month_m: y.month_m,
    month_f: y.month_f,
    annual: y.annual_eur,
    tag: y.tax_kind === "ostvareno" ? "po zakonu" : "procjena",
  }));
  return [...decided, ...projected];
}

function RatesTable({ data }: { data: Funding }) {
  const rows = rateRows(data);
  const max = Math.max(...rows.map((r) => r.month_f));
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-muted border-b border-border">
            <th className="p-3 font-semibold">Odluka</th>
            <th className="p-3 font-semibold">Vrijedi</th>
            <th className="p-3 font-semibold hidden sm:table-cell">M / Ž</th>
            <th className="p-3 font-semibold">Mjesečno po mandatu</th>
            <th className="p-3 font-semibold text-right hidden sm:table-cell">Godišnji iznos</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={`border-b border-border/70 ${r.nn ? "" : "bg-surface/50"}`}>
              <td className="p-3 whitespace-nowrap">
                {r.nn ? (
                  <a href={r.url ?? undefined} target="_blank" rel="noopener" className="inline-flex items-center gap-1">
                    NN {r.nn} <ExternalLink size={12} />
                  </a>
                ) : (
                  <span className="font-semibold text-navy">{r.from.slice(0, 4)}.</span>
                )}
                {r.tag && <div className="text-[11px] text-muted">{r.tag}</div>}
              </td>
              <td className="p-3 whitespace-nowrap text-muted tabular-nums">
                {formatDate(r.from)} – {formatDate(r.to)}
              </td>
              <td className="p-3 tabular-nums whitespace-nowrap hidden sm:table-cell">{r.mps}</td>
              <td className="p-3">
                <div className="space-y-1 min-w-48">
                  {([["M", r.month_m, MALE], ["Ž", r.month_f, FEMALE]] as const).map(([k, v, c]) => (
                    <div key={k} className="grid grid-cols-[1rem_1fr_6.5rem] items-center gap-2 text-xs">
                      <span className="text-muted">{k}</span>
                      <span className="h-2 rounded-full bg-surface overflow-hidden">
                        <span
                          className="block h-full"
                          style={{ width: `${(100 * v) / max}%`, background: c, opacity: r.nn ? 1 : 0.55 }}
                        />
                      </span>
                      <span className="tabular-nums text-right">{eur(v)}</span>
                    </div>
                  ))}
                </div>
              </td>
              <td className="p-3 text-right tabular-nums whitespace-nowrap hidden sm:table-cell">
                {mil(r.annual)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const KIND_LABEL = { ostvareno: "ostvareno", plan: "plan", projekcija: "projekcija" } as const;

const signedPct = (g: number | null | undefined) =>
  g == null ? "" : `${g > 0 ? "+" : g < 0 ? "−" : ""}${Math.abs(g).toLocaleString("hr-HR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}\u00a0%`;

function growthWindow(data: Funding) {
  const macro = new Map((data.macro?.years ?? []).map((y) => [y.year, y]));
  const tax = new Map(data.taxes.map((t) => [t.year, t]));
  // Od temelja za prvu godinu 10. saziva (2020. ← porezi 2018.) do
  // zadnje godine za koju postoje i ostvareni porezi i Eurostatovi podaci.
  const first = Number(data.previous.start.slice(0, 4)) - 2;
  let last = first;
  for (let y = first + 1; tax.get(y)?.kind === "ostvareno" && macro.get(y)?.gdp_nominal_meur != null; y++) last = y;
  if (last === first) return null;
  let prices = 1;
  let real = 1;
  for (let y = first + 1; y <= last; y++) {
    prices *= 1 + (macro.get(y)?.hicp_pct ?? 0) / 100;
    real *= 1 + (macro.get(y)?.gdp_real_pct ?? 0) / 100;
  }
  return {
    first,
    last,
    tax: tax.get(last)!.tax_revenue_eur / tax.get(first)!.tax_revenue_eur - 1,
    nominal: macro.get(last)!.gdp_nominal_meur! / macro.get(first)!.gdp_nominal_meur! - 1,
    prices: prices - 1,
    real: real - 1,
  };
}

function MacroSummary({ data }: { data: Funding }) {
  const w = growthWindow(data);
  if (!w) return null;
  const pp = (g: number) => signedPct(100 * g);
  const tiles = [
    { label: `Novac strankama ${w.first + 2}. → ${w.last + 2}.`, value: pp(w.tax), note: `= porezni prihodi ${w.first}. → ${w.last}.`, accent: true },
    { label: `Nominalni BDP ${w.first}. → ${w.last}.`, value: pp(w.nominal), note: "gospodarstvo u tekućim cijenama" },
    { label: `Cijene ${w.first}. → ${w.last}.`, value: pp(w.prices), note: "kumulativna inflacija (HICP)" },
    { label: `Realni BDP ${w.first}. → ${w.last}.`, value: pp(w.real), note: "gospodarstvo bez inflacije" },
  ];
  const realGain = (1 + w.tax) / (1 + w.prices) - 1;
  return (
    <>
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4 mb-3">
        {tiles.map((t) => (
          <div key={t.label} className="card p-4">
            <div className="field-label">{t.label}</div>
            <div className={`text-xl sm:text-2xl font-extrabold tabular-nums ${t.accent ? "text-flag-red" : "text-navy"}`}>{t.value}</div>
            <div className="text-xs text-muted mt-1">{t.note}</div>
          </div>
        ))}
      </div>
      <p className="text-sm text-navy-700 mb-4 max-w-3xl leading-relaxed">
        Od {w.first}. do {w.last}. porezni prihodi državnog proračuna porasli
        su {pp(w.tax)}, nominalni BDP {pp(w.nominal)}, a cijene {pp(w.prices)}.
        Kad se oduzme inflacija, porezni prihodi realno su veći za oko{" "}
        {Math.round(100 * realGain)}&nbsp;%. Novac strankama prati ih s dvije godine zakašnjenja:
        iznos za {w.last + 2}. viši je za {pp(w.tax)} nego za {w.first + 2}.
      </p>
    </>
  );
}

function TaxTable({ data }: { data: Funding }) {
  const rows = data.taxes.filter((t) => t.year >= 2018 && t.year <= Number(data.projection.end.slice(0, 4)) - 2);
  const macro = new Map((data.macro?.years ?? []).map((y) => [y.year, y]));
  const th = "p-3 font-semibold text-right";
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-muted border-b border-border align-bottom">
            <th className="p-3 font-semibold">Godina</th>
            <th className={th}>Porezni prihodi</th>
            <th className={th}>Rast poreza</th>
            <th className={th}>Nominalni BDP</th>
            <th className={th}>Realni BDP</th>
            <th className={th}>Inflacija</th>
            <th className={th}>Porezi / BDP</th>
            <th className="p-3 font-semibold border-l border-border">→ Strankama</th>
            <th className={th}>Iznos</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => {
            const prev = data.taxes.find((x) => x.year === t.year - 1);
            const g = prev ? t.tax_revenue_eur / prev.tax_revenue_eur - 1 : null;
            const m = macro.get(t.year);
            const mp = macro.get(t.year - 1);
            const nom = m?.gdp_nominal_meur && mp?.gdp_nominal_meur ? m.gdp_nominal_meur / mp.gdp_nominal_meur - 1 : null;
            const share = m?.gdp_nominal_meur && t.kind === "ostvareno" ? t.tax_revenue_eur / 1e6 / m.gdp_nominal_meur : null;
            const neg = (v: number | null | undefined) => (v != null && v < 0 ? "text-flag-red" : "");
            const td = "p-3 text-right tabular-nums whitespace-nowrap";
            return (
              <tr key={t.year} className={`border-b border-border/70 ${t.kind === "ostvareno" ? "" : "bg-surface/50"}`}>
                <td className="p-3 whitespace-nowrap">
                  <a href={t.source_url} target="_blank" rel="noopener">{t.year}.</a>
                  <span className="text-[11px] text-muted ml-1.5">{KIND_LABEL[t.kind]}</span>
                </td>
                <td className={td}>
                  {(t.tax_revenue_eur / 1e9).toLocaleString("hr-HR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} mlrd. €
                </td>
                <td className={`${td} font-semibold ${neg(g)}`}>{g == null ? "" : signedPct(100 * g)}</td>
                <td className={`${td} ${neg(nom)}`}>{nom == null ? "" : signedPct(100 * nom)}</td>
                <td className={`${td} ${neg(m?.gdp_real_pct)}`}>{signedPct(m?.gdp_real_pct)}</td>
                <td className={td}>{signedPct(m?.hicp_pct)}</td>
                <td className={td}>
                  {share == null ? "" : (100 * share).toLocaleString("hr-HR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " %"}
                </td>
                <td className="p-3 whitespace-nowrap border-l border-border">{t.year + 2}.</td>
                <td className="p-3 text-right tabular-nums whitespace-nowrap font-semibold text-navy">
                  {mil(t.tax_revenue_eur * 0.00075)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Projection({ data, catalog }: { data: Funding; catalog: Map<string, Party> }) {
  const pr = data.projection;
  const prev = new Map(data.previous.parties.map((p) => [p.name, p.total_eur]));
  const y27 = pr.years.find((y) => y.tax_kind === "ostvareno");
  const yEst = pr.years.find((y) => y.tax_kind !== "ostvareno");
  return (
    <>
      <h2 className="mt-12 mb-1 text-xl font-bold text-navy">Do kraja saziva ({formatDate(pr.end)})</h2>
      <p className="text-sm text-muted mb-4 max-w-3xl">
        {pr.open_periods.join(", ")} je već raspoređeno odlukom za {data.year}.
        {y27 && (
          <>
            {" "}Iznos za {y27.year}. nije procjena: zakon ga veže uz porezne
            prihode {y27.tax_year}., koji su objavljeni u{" "}
            <a href={y27.tax_source ?? undefined} target="_blank" rel="noopener">izvještaju o izvršenju proračuna</a>.
          </>
        )}
        {yEst && (
          <>
            {" "}Za {yEst.year}. porezni prihodi {yEst.tax_year}. još nisu poznati
            pa se koristi {yEst.tax_kind === "plan" ? "plan iz proračuna" : "projekcija iz proračuna"}
            {yEst.alt && (
              <>
                ; ako se nastavi trend iz prvog polugodišta {yEst.tax_year}.
                (+{(100 * yEst.alt.growth).toLocaleString("hr-HR", { maximumFractionDigits: 1 })} %),
                iznos bi bio nešto veći
              </>
            )}
            .
          </>
        )}
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          label="11. saziv ukupno (procjena)"
          value={`≈ ${mil(pr.saziv_total_eur)}`}
          note={pr.saziv_total_alt_eur > pr.saziv_total_eur ? `do ${mil(pr.saziv_total_alt_eur)} po trendu poreza` : undefined}
          accent
        />
        <Kpi label="Još do kraja saziva" value={mil(pr.projected_eur)} note={`od ${formatDate(data.as_of)}`} />
        {y27 && (
          <Kpi
            label={`${y27.year}. – po zakonu`}
            value={mil(y27.annual_eur)}
            note={`${eur(y27.month_m)} / ${eur(y27.month_f)} mjesečno po mandatu (M / Ž)`}
          />
        )}
        {yEst && (
          <Kpi
            label={`${yEst.year}. do ${formatDate(pr.end)} – procjena`}
            value={mil(yEst.amount_eur)}
            note={`${eur(yEst.month_m)} / ${eur(yEst.month_f)} mjesečno (M / Ž)`}
          />
        )}
      </div>

      <div className="card overflow-x-auto mt-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider text-muted border-b border-border">
              <th className="p-3 font-semibold">Primatelj</th>
              <th className="p-3 font-semibold text-right hidden md:table-cell">10. saziv</th>
              <th className="p-3 font-semibold text-right hidden sm:table-cell">11. dosad</th>
              <th className="p-3 font-semibold text-right">Do kraja</th>
              <th className="p-3 font-semibold text-right">11. saziv ukupno</th>
              <th className="p-3 font-semibold text-right hidden md:table-cell">vs 10.</th>
            </tr>
          </thead>
          <tbody>
            {data.parties.map((p) => {
              const x = pr.parties[p.name];
              const before = prev.get(p.name);
              const delta = before ? x.saziv_total_eur / before - 1 : null;
              return (
                <tr key={p.name} className="border-b border-border/70">
                  <td className="p-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <PartyAvatar size={28} party={catalogAvatar(p, catalog)} />
                      <span className="font-semibold text-navy leading-snug">{p.name}</span>
                    </div>
                  </td>
                  <td className="p-3 text-right tabular-nums whitespace-nowrap text-muted hidden md:table-cell">
                    {before ? eur(before, 0) : "–"}
                  </td>
                  <td className="p-3 text-right tabular-nums whitespace-nowrap hidden sm:table-cell">{eur(p.total_eur, 0)}</td>
                  <td className="p-3 text-right tabular-nums whitespace-nowrap text-muted">+{eur(x.projected_eur, 0)}</td>
                  <td className="p-3 text-right tabular-nums whitespace-nowrap font-bold text-navy">{eur(x.saziv_total_eur, 0)}</td>
                  <td className="p-3 text-right tabular-nums whitespace-nowrap hidden md:table-cell">
                    {delta == null ? <span className="text-muted">novo</span> : `${delta > 0 ? "+" : ""}${Math.round(100 * delta)} %`}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="font-bold text-navy">
              <td className="p-3">Ukupno</td>
              <td className="p-3 text-right tabular-nums whitespace-nowrap hidden md:table-cell">{eur(data.previous.received_eur, 0)}</td>
              <td className="p-3 text-right tabular-nums whitespace-nowrap hidden sm:table-cell">{eur(data.totals.received_eur, 0)}</td>
              <td className="p-3 text-right tabular-nums whitespace-nowrap">+{eur(pr.projected_eur, 0)}</td>
              <td className="p-3 text-right tabular-nums whitespace-nowrap text-flag-red">{eur(pr.saziv_total_eur, 0)}</td>
              <td className="p-3 text-right tabular-nums whitespace-nowrap hidden md:table-cell">
                +{Math.round(100 * (pr.saziv_total_eur / data.previous.received_eur - 1))} %
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      <ul className="text-xs text-muted mt-2 space-y-0.5 list-disc pl-4">
        {pr.assumptions.map((a) => (
          <li key={a}>{a}</li>
        ))}
        <li>
          „vs 10.” uspoređuje cijeli 11. saziv (s procjenom) s 10. sazivom, za stranke koje su primale novac u oba.
          10. saziv trajao je kraće ({formatDate(data.previous.start)} – {formatDate(data.previous.end)}, 3 godine i
          10 mjeseci), pa dio razlike dolazi i od toga, ne samo od rasta poreznih prihoda.
        </li>
      </ul>
    </>
  );
}

function Previous({ data, catalog }: { data: Funding; catalog: Map<string, Party> }) {
  const pv = data.previous;
  const first = pv.rates[0];
  const last = pv.rates[pv.rates.length - 1];
  const max = Math.max(...pv.parties.map((p) => p.total_eur));
  return (
    <>
      <h2 className="mt-12 mb-1 text-xl font-bold text-navy">
        10. saziv ({formatDate(pv.start)} – {formatDate(pv.end)})
      </h2>
      <p className="text-sm text-muted mb-4 max-w-3xl">
        Isti obračun za prethodni saziv, iz {pv.rates.length} odluka Odbora.
        Zbroj po godinama poklapa se sa Saborovim izvješćima za 2021.–2023.,
        a 2024. (podijeljena između dva saziva) s izvješćem za 2024. Mandati su
        oni iz posljednje odluke saziva.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Kpi label="10. saziv ukupno" value={mil(pv.received_eur)} note={`${pv.parties.length} primatelja`} accent />
        <Kpi label="Po mandatu mjesečno, 2020." value={`${eur(first.month_m)}`} note={`zastupnica ${eur(first.month_f)}`} />
        <Kpi label="Po mandatu mjesečno, 2024." value={`${eur(last.month_m)}`} note={`zastupnica ${eur(last.month_f)}`} />
      </div>
      <div className="card overflow-x-auto mt-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider text-muted border-b border-border">
              <th className="p-3 font-semibold">Primatelj</th>
              <th className="p-3 font-semibold">Mandati M / Ž</th>
              <th className="p-3 font-semibold text-right">Ukupno 10. saziv</th>
            </tr>
          </thead>
          <tbody>
            {pv.parties.map((p) => (
              <tr key={p.name} className="border-b border-border/70">
                <td className="p-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <PartyAvatar size={28} party={catalogAvatar(p, catalog)} />
                    <div className="min-w-0">
                      <div className="font-semibold text-navy leading-snug">{p.name}</div>
                      {p.independent && <div className="text-xs text-muted">zastupnik nacionalne manjine · nezavisni zastupnik</div>}
                    </div>
                  </div>
                </td>
                <td className="p-3 tabular-nums whitespace-nowrap">
                  <span style={{ color: MALE }} className="font-semibold">{p.mps_male}</span>
                  <span className="text-muted"> / </span>
                  <span style={{ color: FEMALE }} className="font-semibold">{p.mps_female}</span>
                </td>
                <td className="p-3 text-right">
                  <div className="tabular-nums whitespace-nowrap font-bold text-navy">{eur(p.total_eur)}</div>
                  <div className="h-1.5 mt-1 ml-auto max-w-40 rounded-full bg-surface overflow-hidden">
                    <div className="h-full bg-navy/70 ml-auto" style={{ width: `${(100 * p.total_eur) / max}%` }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Sources({ data }: { data: Funding }) {
  return (
    <section className="mt-12 grid gap-6 md:grid-cols-2 text-sm">
      <div>
        <h2 className="text-lg font-bold text-navy mb-2">Izvori</h2>
        <ul className="space-y-1.5 text-navy-700">
          <li>
            <a href="https://narodne-novine.nn.hr/clanci/sluzbeni/2019_03_29_602.html" target="_blank" rel="noopener">
              Zakon o financiranju političkih aktivnosti, izborne promidžbe i referenduma
            </a>{" "}
            (NN 29/19, 98/19), čl. 5.–11.
          </li>
          <li>
            Odluke Odbora za Ustav, Poslovnik i politički sustav o raspoređivanju
            sredstava:{" "}
            {[...data.previous.rates, ...data.rates].map((r, i) => (
              <Fragment key={r.nn}>
                {i > 0 && ", "}
                <a href={r.url} target="_blank" rel="noopener">NN {r.nn}</a>
              </Fragment>
            ))}
          </li>
          {data.reports.map((r) => (
            <li key={r.year}>
              <a href={r.page_url} target="_blank" rel="noopener">
                Izvješće o raspoređenim i isplaćenim sredstvima za {r.year}.
              </a>{" "}
              (Hrvatski sabor, čl. 11.): raspoređeno {eur(r.allocated_eur)}, isplaćeno {eur(r.paid_eur)}
              {r.currency === "HRK" && " (preračunato iz kuna)"}
            </li>
          ))}
          <li>
            Godišnji izvještaji o izvršenju državnog proračuna (Narodne novine) –
            porezni prihodi, skupina 61:{" "}
            {data.taxes.filter((t) => t.kind === "ostvareno" && t.year >= 2018).map((t, i) => (
              <Fragment key={t.year}>
                {i > 0 && ", "}
                <a href={t.source_url} target="_blank" rel="noopener">{t.year}.</a>
              </Fragment>
            ))}
            ; plan i projekcije iz Državnog proračuna za 2026. (NN 152/2025)
          </li>
          <li>
            <a href="https://www.sabor.hr/hr/zastupnici" target="_blank" rel="noopener">sabor.hr</a>{" "}
            – raspored i profili zastupnika (spol, lista s koje su izabrani), stanje{" "}
            {formatDate(data.seated_fetched_at.slice(0, 10))}
          </li>
        </ul>
      </div>
      <div>
        <h2 className="text-lg font-bold text-navy mb-2">Napomene</h2>
        <ul className="space-y-1.5 text-muted list-disc pl-4">
          <li>
            Godišnji zbroj po svakom primatelju poklapa se sa Saborovim
            izvješćima o raspoređenim sredstvima za 2021.–2025. ({data.checks.rows}{" "}
            usporedbi, odstupanje najviše {data.checks.max_diff.toLocaleString("hr-HR")} zbog
            zaokruživanja).
          </li>
          <li>
            „Raspoređeno” znači iznos po odlukama za tromjesečja koja su
            završila do {formatDate(data.as_of)} Isplate za 2026. Sabor će
            objaviti u izvješću do 1. 3. 2027.
          </li>
          <li>
            Pet zastupnika nacionalnih manjina odluka financira osobno, kao
            nezavisne zastupnike. Za tri srpska manjinska zastupnika novac ide
            stranci koja ih je kandidirala (SDSS).
          </li>
          <li>
            Iznosi ne uključuju naknade za izbornu promidžbu, plaće
            zastupnika ni sredstva za rad klubova zastupnika. To su odvojene
            stavke proračuna.
          </li>
        </ul>
      </div>
    </section>
  );
}
