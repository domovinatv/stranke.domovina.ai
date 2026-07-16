import { MapPin } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { loadParties } from "@/lib/data";
import type { Party } from "@/lib/types";
import { PartyCard } from "@/components/PartyCard";
import { PageSpinner } from "@/components/PageSpinner";

export default function CityRoute() {
  const { name = "" } = useParams();
  const decoded = decodeURIComponent(name);
  const [parties, setParties] = useState<Party[] | null>(null);

  useEffect(() => {
    loadParties().then(setParties);
  }, []);

  useEffect(() => {
    document.title = `${decoded} · DOMOVINA Stranke`;
  }, [decoded]);

  const filtered = useMemo(
    () => (parties ? parties.filter((p) => p.city === decoded) : []),
    [parties, decoded],
  );

  if (!parties) return <PageSpinner />;

  if (filtered.length === 0) {
    return (
      <div className="container-page py-16 text-center">
        <h1 className="text-2xl font-bold text-navy">Nepoznat grad</h1>
        <Link to="/" className="btn-primary mt-6 inline-flex">
          ← Popis stranaka
        </Link>
      </div>
    );
  }

  const active = filtered.filter((p) => p.status === "AKTIVAN").length;
  const defunct = filtered.filter((p) => p.status === "PRESTANAK").length;

  return (
    <section className="container-page py-6 sm:py-10">
      <Link to="/" className="text-sm text-muted hover:text-flag-red inline-block mb-4">
        ← Natrag na popis
      </Link>

      <div className="card p-6 mb-6 bg-gradient-to-br from-surface to-white">
        <div className="pill mb-2 inline-flex items-center gap-1.5"><MapPin size={13} /> Grad</div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-navy">
          {decoded}
        </h1>
        <p className="text-muted mt-2">
          <span className="font-medium text-navy">{filtered.length}</span>{" "}
          {filtered.length === 1 ? "stranka" : "stranaka"} ·{" "}
          <span className="text-emerald-700">{active} aktivnih</span>
          {defunct > 0 && (
            <>
              {" "}· <span className="text-slate-500">{defunct} ugašenih</span>
            </>
          )}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
        {filtered.map((p) => (
          <PartyCard key={p.id} party={p} />
        ))}
      </div>
    </section>
  );
}
