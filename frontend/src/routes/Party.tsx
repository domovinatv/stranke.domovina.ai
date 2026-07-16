import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  formatDate,
  googleMapsUrl,
  loadParties,
  loadPartyDetail,
  yearOf,
} from "@/lib/data";
import {
  Cake,
  ExternalLink,
  Landmark,
  MapPin,
  Phone,
  ScrollText,
  Smartphone,
  Users,
} from "lucide-react";
import type { Party, PartyDetail, PartyFunction } from "@/lib/types";
import { PageSpinner } from "@/components/PageSpinner";
import { PartyAvatar } from "@/components/PartyAvatar";
import { StatusBadge } from "@/components/StatusBadge";

export default function PartyRoute() {
  const { slug = "" } = useParams();
  const [party, setParty] = useState<Party | null>(null);
  const [detail, setDetail] = useState<PartyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setParty(null);
    setDetail(null);
    setError(null);
    Promise.all([loadParties(), loadPartyDetail(slug)])
      .then(([parties, d]) => {
        if (!active) return;
        const p = parties.find((x) => x.slug === slug);
        if (!p) {
          setError("Stranka nije pronađena.");
          return;
        }
        setParty(p);
        setDetail(d);
        document.title = `${p.canonical_name} · DOMOVINA Stranke`;
      })
      .catch(() => active && setError("Stranka nije pronađena."));
    return () => {
      active = false;
    };
  }, [slug]);

  if (error) {
    return (
      <div className="container-page py-16 text-center">
        <h1 className="text-2xl font-bold text-navy">{error}</h1>
        <Link to="/" className="btn-primary mt-6 inline-flex">
          ← Popis stranaka
        </Link>
      </div>
    );
  }

  if (!party || !detail) return <PageSpinner />;

  const regYear = yearOf(party.registered_at);

  return (
    <article className="container-page py-6 sm:py-10">
      <Link to="/" className="text-sm text-muted hover:text-flag-red inline-block mb-4">
        ← Natrag na popis
      </Link>

      <div className="card overflow-hidden">
        <div className="p-6 sm:p-8 flex flex-col sm:flex-row items-start gap-6 border-b border-border bg-gradient-to-br from-surface to-white">
          <PartyAvatar party={party} size={112} />
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl sm:text-3xl font-extrabold text-navy text-balance">
              {party.canonical_name}
            </h1>
            {party.short_name && party.short_name !== party.canonical_name && (
              <div className="text-sm text-muted mt-1">
                Kraći naziv: <span className="font-medium">{party.short_name}</span>
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-2 items-center text-sm">
              <StatusBadge status={party.status} size="md" />
              {party.city && (
                <Link
                  to={`/grad/${encodeURIComponent(party.city)}`}
                  className="pill !text-navy hover:!text-flag-red"
                >
                  <span className="inline-flex items-center gap-1"><MapPin size={13} /> {party.city}</span>
                </Link>
              )}
              {party.county && (
                <span className="pill">{party.county.replace(" županija", "")}</span>
              )}
              {regYear && (
                <span className="pill inline-flex items-center gap-1"><Cake size={13} /> reg. {regYear}.</span>
              )}
            </div>
            {party.wiki_url && (
              <div className="mt-4 flex items-center gap-2 flex-wrap">
                <a
                  href={party.wiki_url}
                  target="_blank"
                  rel="noopener"
                  className="btn-ghost text-xs"
                >
                  <ExternalLink size={14} /> Wikipedija
                </a>
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-border">
          <RegistryPanel party={party} detail={detail} />
          <ContactPanel party={party} />
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mt-4">
        {detail.people.length > 0 && <PeoplePanel detail={detail} />}
        {detail.functions.length > 0 && <FunctionsPanel detail={detail} />}
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mt-4">
        {detail.aliases.length > 0 && <AliasesPanel detail={detail} />}
        {detail.notes && <NotesPanel notes={detail.notes} />}
      </div>

      {party.lat != null && party.lng != null && <MiniMap party={party} />}
    </article>
  );
}

function RegistryPanel({ party, detail }: { party: Party; detail: PartyDetail }) {
  return (
    <div className="p-6 space-y-3">
      <h2 className="field-label">
        <span className="inline-flex items-center gap-1.5"><Landmark size={13} /> Registar</span>
      </h2>
      {party.oib && <Row k="OIB" v={<span className="font-mono text-sm">{party.oib}</span>} />}
      {party.reg_number && (
        <Row k="Registarski broj" v={<span className="font-mono text-sm">{party.reg_number}</span>} />
      )}
      {detail.book_number != null && (
        <Row k="Knjiga registra" v={<span className="tabular-nums">{detail.book_number}</span>} />
      )}
      <Row
        k="Status"
        v={
          <>
            <StatusBadge status={party.status} size="xs" />
            {party.status_date && (
              <span className="text-xs text-muted ml-1.5">
                od {formatDate(party.status_date)}
              </span>
            )}
          </>
        }
      />
      {party.registered_at && (
        <Row k="Upis u registar" v={formatDate(party.registered_at)} />
      )}
      {detail.seat && <Row k="Sjedište" v={detail.seat} />}
      {(party.founded_place || party.founded_date) && (
        <Row
          k="Osnovana"
          v={
            <>
              {party.founded_place}
              {party.founded_place && party.founded_date && ", "}
              {formatDate(party.founded_date)}
            </>
          }
        />
      )}
    </div>
  );
}

function ContactPanel({ party }: { party: Party }) {
  return (
    <div className="p-6 space-y-3">
      <h2 className="field-label">Kontakt</h2>
      {party.address && (
        <Row
          k="Adresa"
          v={
            <>
              {party.address}
              {party.city && `, ${party.city}`}
            </>
          }
        />
      )}
      {party.phone && (
        <Row
          k={
            party.phone_kind === "mobile" ? (
              <span className="inline-flex items-center gap-1"><Smartphone size={12} /> Mobitel</span>
            ) : party.phone_kind === "landline" ? (
              <span className="inline-flex items-center gap-1"><Phone size={12} /> Fiksni</span>
            ) : (
              "Telefon"
            )
          }
          v={
            <a href={`tel:${party.phone_e164 || party.phone}`} className="text-navy hover:text-flag-red">
              {party.phone}
            </a>
          }
        />
      )}
      {party.email && (
        <Row
          k="Email"
          v={
            <a href={`mailto:${party.email}`} className="text-navy hover:text-flag-red break-all">
              {party.email}
            </a>
          }
        />
      )}
      {party.website && (
        <Row
          k="Web"
          v={
            <a href={party.website} target="_blank" rel="noopener" className="break-all">
              {party.website}
            </a>
          }
        />
      )}
      {party.president && <Row k="Predsjednik/ca" v={party.president} />}

      <div className="flex gap-2 pt-2 flex-wrap">
        {party.fb_url && (
          <a href={party.fb_url} target="_blank" rel="noopener" className="btn-ghost !text-blue-700 !border-blue-200 hover:!bg-blue-50">
            Facebook
          </a>
        )}
        {party.ig_url && (
          <a href={party.ig_url} target="_blank" rel="noopener" className="btn-ghost !text-pink-700 !border-pink-200 hover:!bg-pink-50">
            Instagram
          </a>
        )}
        {party.x_url && (
          <a href={party.x_url} target="_blank" rel="noopener" className="btn-ghost">
            X
          </a>
        )}
      </div>

      {!party.phone && !party.email && !party.address && !party.website && !party.fb_url && (
        <p className="text-sm text-muted italic">Nema poznatih kontaktnih podataka.</p>
      )}
    </div>
  );
}

function PeoplePanel({ detail }: { detail: PartyDetail }) {
  return (
    <section className="card p-6">
      <h2 className="field-label">
        <span className="inline-flex items-center gap-1.5"><Users size={13} /> Osobe u registru</span>
      </h2>
      <ul className="mt-2 space-y-1.5 text-sm">
        {detail.people.map((p, i) => (
          <li key={i} className="flex items-center gap-2 justify-between">
            <span className="text-navy truncate">
              {p.full_name}
              {p.represents ? (
                <span
                  className="text-xs text-muted ml-1"
                  title="Ovlaštena osoba za zastupanje"
                >
                  (zastupa)
                </span>
              ) : null}
            </span>
            {p.role && (
              <span className="text-muted text-xs uppercase tracking-wide whitespace-nowrap">
                {p.role.toLowerCase()}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** "2016 – danas" style range from ISO mandate dates. */
function mandateRange(f: PartyFunction): string {
  const from = yearOf(f.mandate_start) ?? "?";
  const to = f.mandate_end ? yearOf(f.mandate_end) : "danas";
  return `${from} – ${to}`;
}

function FunctionsPanel({ detail }: { detail: PartyDetail }) {
  const groups = new Map<string, PartyFunction[]>();
  for (const f of detail.functions) {
    const list = groups.get(f.function) || [];
    list.push(f);
    groups.set(f.function, list);
  }
  return (
    <section className="card p-6">
      <h2 className="field-label">
        <span className="inline-flex items-center gap-1.5"><ScrollText size={13} /> Funkcije kroz povijest</span>
      </h2>
      <div className="mt-2 space-y-4">
        {Array.from(groups.entries()).map(([fn, list]) => (
          <div key={fn}>
            <div className="text-xs font-semibold text-navy uppercase tracking-wide mb-1">
              {fn}
            </div>
            <ul className="space-y-1 text-sm">
              {list
                .slice()
                .sort((a, b) => (b.mandate_start || "").localeCompare(a.mandate_start || ""))
                .map((f, i) => (
                  <li key={i} className="flex items-center gap-2 justify-between">
                    <span className="text-navy-700 truncate">{f.holder}</span>
                    <span className="text-muted tabular-nums text-xs whitespace-nowrap">
                      {mandateRange(f)}
                    </span>
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted">Izvor: NSK imenik političkih stranaka.</p>
    </section>
  );
}

function AliasesPanel({ detail }: { detail: PartyDetail }) {
  return (
    <section className="card p-6">
      <h2 className="field-label">Drugi nazivi</h2>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {detail.aliases.map((a, i) => (
          <span key={i} className="pill">{a.alias}</span>
        ))}
      </div>
    </section>
  );
}

function NotesPanel({ notes }: { notes: string }) {
  return (
    <section className="card p-6">
      <h2 className="field-label">Napomene iz registra</h2>
      <p className="mt-2 text-sm text-navy-700 whitespace-pre-line leading-relaxed">
        {notes}
      </p>
    </section>
  );
}

/**
 * Mini karta sjedišta — maplibre se učitava lijeno (dynamic import) da detail
 * ruta ne povuče cijeli maplibre bundle prije nego što je karta zaista potrebna.
 */
function MiniMap({ party }: { party: Party }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const gmaps = googleMapsUrl(party);

  useEffect(() => {
    if (!containerRef.current || party.lat == null || party.lng == null) return;
    let map: { remove(): void } | null = null;
    let cancelled = false;

    Promise.all([
      import("maplibre-gl"),
      import("maplibre-gl/dist/maplibre-gl.css"),
    ]).then(([mod]) => {
      if (cancelled || !containerRef.current) return;
      const maplibregl = mod.default;
      const m = new maplibregl.Map({
        container: containerRef.current,
        style: {
          version: 8,
          sources: {
            carto: {
              type: "raster",
              tiles: [
                "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
                "https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
                "https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
              ],
              tileSize: 256,
              attribution:
                '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · © <a href="https://carto.com/attributions">CARTO</a>',
            },
          },
          layers: [{ id: "carto", type: "raster", source: "carto" }],
        },
        center: [party.lng!, party.lat!],
        zoom: 14,
        interactive: false,
        attributionControl: { compact: true },
      });
      new maplibregl.Marker({ color: "#002F6C" })
        .setLngLat([party.lng!, party.lat!])
        .addTo(m);
      map = m;
    });

    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [party.lat, party.lng]);

  return (
    <section className="mt-4 card overflow-hidden">
      <div className="p-4 flex items-center justify-between gap-3 flex-wrap">
        <div className="field-label !mb-0">Sjedište na karti</div>
        {gmaps && (
          <a href={gmaps} target="_blank" rel="noopener" className="btn-ghost text-xs">
            Google Maps ↗
          </a>
        )}
      </div>
      <div ref={containerRef} style={{ height: 280 }} />
    </section>
  );
}

function Row({ k, v }: { k: React.ReactNode; v: React.ReactNode }) {
  return (
    <div className="text-sm">
      <span className="text-muted text-xs uppercase tracking-wide">{k}:</span>{" "}
      <span className="text-navy-700">{v}</span>
    </div>
  );
}
