import { ChartColumn } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { loadCities, loadStats } from "@/lib/data";
import type { City, Stats } from "@/lib/types";
import { PageSpinner } from "@/components/PageSpinner";

export default function StatsRoute() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [cities, setCities] = useState<City[] | null>(null);

  useEffect(() => {
    Promise.all([loadStats(), loadCities()]).then(([s, c]) => {
      setStats(s);
      setCities(c);
    });
  }, []);

  if (!stats || !cities) return <PageSpinner />;
  const g = stats.global;

  return (
    <section className="container-page py-6 sm:py-10">
      <header className="mb-8">
        <div className="pill mb-2 inline-flex items-center gap-1.5"><ChartColumn size={13} /> Pokrivenost</div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-navy">
          Statistika kataloga
        </h1>
        <p className="text-muted mt-2 max-w-2xl">
          Kako je popunjen katalog: koliko stranaka ima koje vrste podatka.
          Postoci se računaju prema ukupnoj brojci od{" "}
          <span className="font-medium text-navy">{g.total}</span> stranaka.
        </p>
      </header>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-6 gap-3">
        <StatCard label="Ukupno stranaka" value={g.total} accent />
        <StatCard label="Aktivne" value={g.active} of={g.total} emerald />
        <StatCard label="Ugašene" value={g.defunct} of={g.total} />
        <StatCard label="Pun kontakt" value={g.full_contact} of={g.total} emerald />
        <StatCard label="Mobitel (SMS)" value={g.can_sms} of={g.total} />
        <StatCard label="Telefon (svi)" value={g.can_call} of={g.total} />
        <StatCard label="Email" value={g.can_email} of={g.total} />
        <StatCard label="Adresa" value={g.can_mail} of={g.total} />
        <StatCard label="Online prisutne" value={g.can_web} of={g.total} />
        <StatCard label="Koordinate" value={g.with_geo} of={g.total} />
        <StatCard label="Predsjednik" value={g.with_president} of={g.total} />
        <StatCard label="OIB" value={g.with_oib} of={g.total} />
        <StatCard label="Wikipedija" value={g.with_wiki} of={g.total} />
      </div>

      <h2 className="mt-12 mb-3 text-lg font-bold text-navy">
        Registracije po desetljećima
      </h2>
      <DecadesChart decades={stats.decades} />

      <h2 className="mt-12 mb-3 text-lg font-bold text-navy">Po gradu</h2>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5 gap-2">
        {cities.map((c) => (
          <Link
            key={c.name}
            to={`/grad/${encodeURIComponent(c.name)}`}
            className="card-hover p-3 flex items-center justify-between gap-2"
          >
            <span className="text-sm text-navy truncate">{c.name}</span>
            <span className="text-sm font-bold text-navy tabular-nums whitespace-nowrap">
              {c.n}
              <span className="text-emerald-600 font-medium text-xs ml-1">
                ({c.active})
              </span>
            </span>
          </Link>
        ))}
      </div>
      <p className="text-xs text-muted mt-2">
        Broj u zagradi = trenutno aktivne stranke u gradu.
      </p>
    </section>
  );
}

function DecadesChart({ decades }: { decades: Stats["decades"] }) {
  const max = Math.max(...decades.map((d) => d.n), 1);
  return (
    <div className="card p-6">
      <div className="flex items-end gap-4 sm:gap-8" style={{ height: 220 }}>
        {decades.map((d) => (
          <div key={d.decade} className="flex-1 flex flex-col items-center justify-end h-full gap-2">
            <div className="text-sm font-bold text-navy tabular-nums">{d.n}</div>
            <div
              className="w-full max-w-24 rounded-t-sm bg-navy/85 hover:bg-flag-red transition-colors"
              style={{ height: `${Math.max(4, Math.round((100 * d.n) / max))}%` }}
              title={`${d.decade}: ${d.n} stranaka`}
            />
            <div className="text-xs text-muted">{d.decade}</div>
          </div>
        ))}
      </div>
      <p className="text-xs text-muted mt-3">
        Broj upisa u Registar političkih stranaka po desetljeću registracije.
      </p>
    </div>
  );
}

function StatCard({
  label,
  value,
  of,
  accent,
  emerald,
}: {
  label: string;
  value: number;
  of?: number;
  accent?: boolean;
  emerald?: boolean;
}) {
  const pct = of ? Math.round((100 * value) / of) : null;
  return (
    <div className="card p-4">
      <div className="field-label">{label}</div>
      <div
        className={`text-3xl font-extrabold tabular-nums ${
          emerald ? "text-emerald-600" : accent ? "text-flag-red" : "text-navy"
        }`}
      >
        {value.toLocaleString("hr-HR")}
      </div>
      {pct !== null && (
        <div className="mt-1">
          <div className="h-1.5 rounded-full bg-surface overflow-hidden">
            <div
              className={`h-full ${emerald ? "bg-emerald-500" : "bg-navy"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="text-xs text-muted mt-0.5 tabular-nums">{pct}%</div>
        </div>
      )}
    </div>
  );
}
