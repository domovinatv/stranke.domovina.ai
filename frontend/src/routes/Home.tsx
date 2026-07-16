import { Database, SearchX } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { loadCities, loadParties, loadStats } from "@/lib/data";
import type { City, Party, Stats } from "@/lib/types";
import {
  applyFilter,
  EMPTY_FILTER,
  readFilterFromSearchParams,
  writeFilterToSearchParams,
  type PartyFilter,
} from "@/lib/filter";
import { FilterPanel } from "@/components/FilterPanel";
import { PartyCard } from "@/components/PartyCard";
import { PageSpinner } from "@/components/PageSpinner";

const PAGE_SIZE = 60;

export default function Home() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [parties, setParties] = useState<Party[] | null>(null);
  const [cities, setCities] = useState<City[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [page, setPage] = useState(1);

  const filter = useMemo<PartyFilter>(
    () => readFilterFromSearchParams(searchParams),
    [searchParams],
  );

  useEffect(() => {
    Promise.all([loadParties(), loadCities(), loadStats()]).then(([p, c, s]) => {
      setParties(p);
      setCities(c);
      setStats(s);
    });
  }, []);

  useEffect(() => {
    setPage(1);
  }, [searchParams]);

  if (!parties || !cities || !stats) return <PageSpinner />;

  const filtered = applyFilter(parties, filter);
  const visible = filtered.slice(0, page * PAGE_SIZE);
  const hasMore = visible.length < filtered.length;

  const updateFilter = (next: PartyFilter) => {
    setSearchParams(writeFilterToSearchParams(next), { replace: true });
  };

  return (
    <>
      <Hero stats={stats} />

      <section className="container-page mt-8 mb-16 grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr] 2xl:grid-cols-[320px_1fr]">
        <FilterPanel
          filter={filter}
          onChange={updateFilter}
          onReset={() => updateFilter(EMPTY_FILTER)}
          cities={cities}
          stats={stats}
        />

        <div className="min-w-0">
          <ListHeader
            shown={visible.length}
            total={filtered.length}
            filter={filter}
          />
          {filtered.length === 0 ? (
            <Empty />
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
                {visible.map((p) => (
                  <PartyCard key={p.id} party={p} />
                ))}
              </div>
              {hasMore && (
                <div className="mt-6 flex justify-center">
                  <button
                    onClick={() => setPage((p) => p + 1)}
                    className="btn-ghost"
                  >
                    Učitaj još ({filtered.length - visible.length})
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </section>
    </>
  );
}

function Hero({ stats }: { stats: Stats }) {
  const g = stats.global;
  return (
    <section className="border-b border-border bg-gradient-to-b from-surface to-white">
      <div className="container-page py-12 sm:py-16">
        <div className="max-w-3xl">
          <div className="pill mb-4 inline-flex items-center gap-1.5">
            <Database size={13} /> Otvoreni podaci ·{" "}
            {g.total.toLocaleString("hr-HR")} stranaka
          </div>
          <h1 className="text-balance text-3xl sm:text-5xl font-extrabold tracking-tight text-navy">
            Sve hrvatske političke stranke
            <span className="text-flag-red"> na jednom mjestu</span>
          </h1>
          <p className="mt-4 text-lg text-muted leading-relaxed text-balance">
            Aktivne i ugašene stranke iz Registra od 1990. do danas — kontakti,
            dužnosnici, povijest, koordinate. Pretraži, filtriraj, izvezi.
          </p>
        </div>
        <div className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-3xl 2xl:max-w-5xl">
          <Stat label="Stranaka" value={g.total} accent />
          <Stat label="Aktivnih" value={g.active} suffix={` (${pct(g.active, g.total)})`} />
          <Stat label="S koordinatama" value={g.with_geo} suffix={` (${pct(g.with_geo, g.total)})`} />
          <Stat label="Pun kontakt" value={g.full_contact} suffix={` (${pct(g.full_contact, g.total)})`} />
        </div>
      </div>
    </section>
  );
}

function pct(a: number, b: number): string {
  if (!b) return "0%";
  return `${Math.round((100 * a) / b)}%`;
}

function Stat({
  label,
  value,
  suffix,
  accent,
}: {
  label: string;
  value: number;
  suffix?: string;
  accent?: boolean;
}) {
  return (
    <div className="card p-4">
      <div className="field-label">{label}</div>
      <div
        className={`text-2xl sm:text-3xl font-extrabold tabular-nums ${
          accent ? "text-flag-red" : "text-navy"
        }`}
      >
        {value.toLocaleString("hr-HR")}
      </div>
      {suffix && <div className="text-xs text-muted mt-0.5">{suffix}</div>}
    </div>
  );
}

function ListHeader({
  shown,
  total,
  filter,
}: {
  shown: number;
  total: number;
  filter: PartyFilter;
}) {
  const active =
    filter.q ||
    filter.status !== "active" ||
    filter.city ||
    filter.hasMobile ||
    filter.hasPhone ||
    filter.hasEmail ||
    filter.hasWeb ||
    filter.onlyFull;
  return (
    <div className="flex items-baseline justify-between mb-4 gap-3 flex-wrap">
      <div>
        <h2 className="text-lg font-bold text-navy">
          {total.toLocaleString("hr-HR")}{" "}
          <span className="text-muted font-medium">
            {total === 1 ? "stranka" : total % 10 >= 2 && total % 10 <= 4 && (total % 100 < 12 || total % 100 > 14) ? "stranke" : "stranaka"}
          </span>
          {active && <span className="text-muted text-sm"> (filtrirano)</span>}
        </h2>
        {total > 0 && (
          <div className="text-xs text-muted">
            Prikazano {shown.toLocaleString("hr-HR")}
          </div>
        )}
      </div>
    </div>
  );
}

function Empty() {
  return (
    <div className="card p-12 text-center text-muted">
      <div className="mb-3 grid place-items-center text-muted/50"><SearchX size={44} strokeWidth={1.5} /></div>
      <div className="font-medium text-navy">Nijedna stranka ne odgovara filterima.</div>
      <div className="text-sm mt-1">Resetiraj filtere i pokušaj ponovno.</div>
    </div>
  );
}
