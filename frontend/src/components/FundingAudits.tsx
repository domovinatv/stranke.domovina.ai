import { ChevronDown, ExternalLink } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { AuditParty, AuditYear, Audits, Party } from "@/lib/types";
import { PartyAvatar } from "@/components/PartyAvatar";
import { catalogAvatar } from "@/lib/fundingLive";

const NF0 = new Intl.NumberFormat("hr-HR", { maximumFractionDigits: 0 });
const NF2 = new Intl.NumberFormat("hr-HR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Kratki zapis: 8,74 mil. € ili 456.123 €. */
const money = (n: number | null | undefined) => {
  if (n == null) return "–";
  const sign = n < 0 ? "−" : "";
  const a = Math.abs(n);
  return a >= 1e6 ? `${sign}${NF2.format(a / 1e6)} mil. €` : `${sign}${NF0.format(a)} €`;
};
const signed = (n: number) => (n > 0 ? "+" : "") + money(n);
const share = (a: number | null, b: number | null) =>
  a == null || !b ? "" : `${NF0.format((100 * a) / b)} %`;

function avatarParty(p: AuditParty) {
  return { name: p.name, slug: p.slug, short: p.short, independent: false } as Parameters<typeof catalogAvatar>[0];
}

export function FundingAudits({
  audits,
  catalog,
  hicp,
}: {
  audits: Audits;
  catalog: Map<string, Party>;
  /** Prosječna godišnja inflacija po godini, % (Eurostat HICP). */
  hicp: Map<number, number | null>;
}) {
  const years = useMemo(
    () => [...new Set(audits.parties.flatMap((p) => Object.keys(p.years)))].sort(),
    [audits],
  );
  const [year, setYear] = useState(years[years.length - 1]);
  const [onlyCurrent, setOnlyCurrent] = useState(true);
  const [open, setOpen] = useState<string | null>(null);

  const first = years[0];
  const last = years[years.length - 1];
  const rows = audits.parties.filter((p) => (!onlyCurrent || p.current) && p.years[year]);
  rows.sort((a, b) => (b.years[year].revenue.total ?? 0) - (a.years[year].revenue.total ?? 0));

  // Zbroj za stranke koje imaju i prvu i zadnju godinu, da usporedba bude ista skupina.
  const both = audits.parties.filter((p) => (!onlyCurrent || p.current) && p.years[first] && p.years[last]);
  const sum = (y: string, f: (a: AuditYear) => number | null) => both.reduce((s, p) => s + (f(p.years[y]) ?? 0), 0);
  const equity0 = sum(first, (a) => a.balance.equity);
  const equity1 = sum(last, (a) => a.balance.equity);
  const cash1 = sum(last, (a) => a.balance.cash);
  const liab1 = sum(last, (a) => a.balance.liabilities);
  const between = years.filter((y) => y > first);
  const staff0 = sum(first, (a) => a.expenses.staff);
  const staff1 = sum(last, (a) => a.expenses.staff);
  const prices = between.every((y) => hicp.get(Number(y)) != null)
    ? between.reduce((s, y) => s * (1 + (hicp.get(Number(y)) ?? 0) / 100), 1) - 1
    : null;
  const deficitYears = years.filter((y) => both.reduce((s, p) => s + (p.years[y]?.result ?? 0), 0) < 0);
  const top = [...both].sort((a, b) => (b.years[last].balance.equity ?? 0) - (a.years[last].balance.equity ?? 0))[0];
  const negative = audits.parties.filter((p) => (!onlyCurrent || p.current) && (p.years[last]?.balance.equity ?? 0) < 0);
  const pctAbs = (a: number, b: number) => `${NF0.format(Math.abs((100 * (b - a)) / a))}\u00a0%`;
  const grew = (a: number, b: number) => (b >= a ? "porasli su za" : "smanjili su se za");
  const pct = (a: number, b: number) => `${b - a >= 0 ? "+" : "−"}${NF0.format(Math.abs((100 * (b - a)) / a))} %`;

  const th = "px-2 py-3 font-semibold text-right whitespace-nowrap";
  const td = "px-2 py-2.5 text-right tabular-nums whitespace-nowrap";

  return (
    <>
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4 mb-3">
        <Tile label={`Vlastiti izvori 31. 12. ${first}.`} value={money(equity0)} note="imovina umanjena za obveze" />
        <Tile label={`Vlastiti izvori 31. 12. ${last}.`} value={money(equity1)} note={`${pct(equity0, equity1)} u odnosu na ${first}.`} accent />
        <Tile label={`Novac na računima 31. 12. ${last}.`} value={money(cash1)} note={`obveze ${money(liab1)}`} />
        <Tile label={`Rashodi za zaposlene ${last}.`} value={money(staff1)} note={`${pct(staff0, staff1)} u odnosu na ${first}.`} />
      </div>
      <p className="text-sm text-navy-700 mb-4 max-w-3xl leading-relaxed">
        Zbroj za {both.length} stranaka koje imaju revidirane izvještaje i za {first}. i
        za {last}. Vlastiti izvori su imovina (novac, potraživanja, nekretnine,
        oprema) umanjena za sve obveze, dakle ono što je ostalo od ranijih viškova.
        Od kraja {first}. do kraja {last}. {grew(equity0, equity1)}{" "}
        {pctAbs(equity0, equity1)}
        {prices != null && <>, a cijene su porasle za {pctAbs(1, 1 + prices)}</>}. Rashodi za
        zaposlene {grew(staff0, staff1).replace("li su", "li su")} {pctAbs(staff0, staff1)}.
        {deficitYears.length > 0 && (
          <> Ukupan manjak (više rashoda nego prihoda) ove su stranke imale u{" "}
          {deficitYears.map((y) => `${y}`).join(". i ")}.</>
        )}
        {top && (
          <> Najveći dio rezervi drži {top.short ?? top.name} ({NF0.format((100 * (top.years[last].balance.equity ?? 0)) / equity1)}{"\u00a0"}%),</>
        )}{" "}
        {negative.length > 0 ? (
          <>a {negative.length}{" "}
          {negative.length === 1 ? "stranka je završila" : negative.length < 5 ? "stranke su završile" : "stranaka je završilo"}{" "}
          {last}. s više obveza nego imovine ({negative.map((p) => p.short ?? p.name).join(", ")}).</>
        ) : (
          <>a nijedna nije {last}. imala više obveza nego imovine.</>
        )}
      </p>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        {years.map((y) => (
          <button
            key={y}
            type="button"
            onClick={() => setYear(y)}
            className={`rounded-full border px-3 py-1 text-sm tabular-nums ${y === year ? "bg-navy text-white border-navy" : "border-border text-navy hover:border-navy"}`}
          >
            {y}.
          </button>
        ))}
        <label className="ml-auto inline-flex items-center gap-2 text-sm text-muted">
          <input type="checkbox" checked={onlyCurrent} onChange={(e) => setOnlyCurrent(e.target.checked)} />
          samo stranke u 11. sazivu
        </label>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider text-muted border-b border-border align-bottom">
              <th className="p-3 font-semibold">Stranka</th>
              <th className={th}>Prihodi</th>
              <th className={th}>Državni proračun</th>
              <th className={th}>Rashodi</th>
              <th className={th}>Za zaposlene</th>
              <th className={th}>Višak / manjak</th>
              <th className={`${th} border-l border-border`}>Novac 31. 12.</th>
              <th className={th}>Obveze</th>
              <th className={th}>Vlastiti izvori</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const a = p.years[year];
              const isOpen = open === p.name;
              const neg = (v: number | null | undefined) => (v != null && v < 0 ? "text-flag-red" : "");
              return (
                <Fragment key={p.name}>
                  <tr
                    className="border-b border-border/70 cursor-pointer hover:bg-surface/60"
                    onClick={() => setOpen(isOpen ? null : p.name)}
                  >
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <ChevronDown size={14} className={`text-muted shrink-0 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                        <PartyAvatar size={24} party={catalogAvatar(avatarParty(p), catalog)} />
                        <span className="font-semibold text-navy leading-snug">{p.short ?? p.name}</span>
                      </div>
                    </td>
                    <td className={td}>{money(a.revenue.total)}</td>
                    <td className={td}>
                      {money(a.revenue.state)}
                      <span className="block text-[11px] text-muted">{share(a.revenue.state, a.revenue.total)}</span>
                    </td>
                    <td className={td}>{money(a.expenses.total)}</td>
                    <td className={td}>
                      {money(a.expenses.staff)}
                      <span className="block text-[11px] text-muted">{share(a.expenses.staff, a.expenses.total)}</span>
                    </td>
                    <td className={`${td} font-semibold ${neg(a.result)}`}>{signed(a.result)}</td>
                    <td className={`${td} border-l border-border`}>{money(a.balance.cash)}</td>
                    <td className={td}>
                      {money(a.balance.liabilities)}
                      {a.balance.loans ? <span className="block text-[11px] text-muted">krediti {money(a.balance.loans)}</span> : null}
                    </td>
                    <td className={`${td} font-semibold text-navy ${neg(a.balance.equity)}`}>{money(a.balance.equity)}</td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-surface/50 border-b border-border">
                      <td colSpan={9} className="p-3">
                        <PartyYears p={p} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted mt-2 max-w-3xl">
        Izvor:{" "}
        <a href={audits.source} target="_blank" rel="noopener">Državni ured za reviziju</a>,
        izvješća o obavljenoj financijskoj reviziji političkih stranaka (svako
        izvješće sadrži i usporedne podatke za prethodnu godinu). „Iz državnog
        proračuna“ uključuje i naknadu troškova izborne promidžbe, zato je u
        izbornim godinama veći. Stranke dobivaju novac i iz proračuna županija,
        gradova i općina za svoje vijećnike. Iznosi do 2022. preračunati su iz
        kuna (7,53450 kn/€). Kliknite redak za sve godine i poveznice na izvješća.
      </p>
    </>
  );
}

function PartyYears({ p }: { p: AuditParty }) {
  const ys = Object.keys(p.years).sort();
  const row = (label: string, f: (a: AuditYear) => number | null | undefined, strong = false) => (
    <tr className="border-b border-border/50">
      <th className="py-1.5 pr-3 text-left font-normal text-muted whitespace-nowrap">{label}</th>
      {ys.map((y) => {
        const v = f(p.years[y]);
        return (
          <td key={y} className={`py-1.5 px-2 text-right tabular-nums whitespace-nowrap ${strong ? "font-semibold text-navy" : ""} ${v != null && v < 0 ? "text-flag-red" : ""}`}>
            {money(v)}
          </td>
        );
      })}
    </tr>
  );
  return (
    <div className="overflow-x-auto">
      <div className="mb-2 text-sm font-semibold text-navy">
        {p.slug ? <Link to={`/stranka/${p.slug}`}>{p.name}</Link> : p.name}
      </div>
      <table className="text-xs sm:text-sm">
        <thead>
          <tr className="text-[11px] uppercase tracking-wider text-muted">
            <th />
            {ys.map((y) => (
              <th key={y} className="px-2 py-1 text-right font-semibold">
                <a href={p.years[y].source} target="_blank" rel="noopener" className="inline-flex items-center gap-0.5">
                  {y}. <ExternalLink size={10} />
                </a>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {row("Prihodi ukupno", (a) => a.revenue.total, true)}
          {row("· državni proračun", (a) => a.revenue.state)}
          {row("· lokalni proračuni", (a) => a.revenue.local)}
          {row("· članarine", (a) => a.revenue.members)}
          {row("· donacije", (a) => a.revenue.donations)}
          {row("· drugi prihodi", (a) => a.revenue.other)}
          {row("Rashodi ukupno", (a) => a.expenses.total, true)}
          {row("· zaposleni", (a) => a.expenses.staff)}
          {row("· promidžba", (a) => a.expenses.promo)}
          {row("· ostali materijalni", (a) => a.expenses.material_other)}
          {row("Višak / manjak", (a) => a.result, true)}
          {row("Novac 31. 12.", (a) => a.balance.cash)}
          {row("Obveze 31. 12.", (a) => a.balance.liabilities)}
          {row("· krediti i zajmovi", (a) => a.balance.loans)}
          {row("Vlastiti izvori 31. 12.", (a) => a.balance.equity, true)}
        </tbody>
      </table>
    </div>
  );
}

function Tile({ label, value, note, accent }: { label: string; value: string; note: string; accent?: boolean }) {
  return (
    <div className="card p-4">
      <div className="field-label">{label}</div>
      <div className={`text-xl sm:text-2xl font-extrabold tabular-nums ${accent ? "text-flag-red" : "text-navy"}`}>{value}</div>
      <div className="text-xs text-muted mt-1">{note}</div>
    </div>
  );
}
