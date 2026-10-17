import { ArrowLeft } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { formatDate, loadFunding, loadParties } from "@/lib/data";
import type { Funding, Party } from "@/lib/types";
import {
  OTHER_KEYS,
  buildOther,
  buildSchedule,
  catalogAvatar,
  cumulativeAt,
  liveSlug,
  perSecond,
  publicShare,
  segmentAt,
  type OtherIncome,
  type Schedule,
} from "@/lib/fundingLive";
import { PageSpinner } from "@/components/PageSpinner";
import { PartyAvatar } from "@/components/PartyAvatar";
import {
  F0,
  F4,
  F5,
  OTHER,
  OtherCard,
  ProgressRow,
  PublicCard,
  ShareButton,
  eur,
  useReducedMotion,
} from "./FundingLive";

const NAVY = "#002F6C";
const F1 = new Intl.NumberFormat("hr-HR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export default function FundingLivePartyRoute() {
  const { slug = "" } = useParams();
  const [data, setData] = useState<Funding | null>(null);
  const [catalog, setCatalog] = useState<Map<string, Party>>(new Map());

  useEffect(() => {
    loadFunding().then(setData);
    loadParties()
      .then((ps) => setCatalog(new Map(ps.map((p) => [p.slug, p]))))
      .catch(() => undefined);
  }, []);

  const schedule = useMemo(() => (data ? buildSchedule(data) : null), [data]);
  const other = useMemo(() => (data && schedule ? buildOther(data, schedule) : null), [data, schedule]);
  if (!data || !schedule) return <PageSpinner />;
  const i = schedule.parties.findIndex((p) => liveSlug(p) === slug);
  if (i < 0) {
    return (
      <section className="container-page py-10">
        <Link to="/financiranje/uzivo" className="inline-flex items-center gap-1 text-sm text-muted hover:text-navy mb-4">
          <ArrowLeft size={14} /> Javni novac uživo
        </Link>
        <p className="text-navy">Ova stranka u 11. sazivu ne prima novac iz državnog proračuna.</p>
      </section>
    );
  }
  return <PartyLive key={slug} data={data} s={schedule} other={other} i={i} catalog={catalog} />;
}

/** Ostali prihodi samo jednog primatelja, u obliku koji OtherCard očekuje. */
function partyOther(other: OtherIncome | null, i: number): OtherIncome | null {
  if (!other || Number.isNaN(other.byParty[i])) return null;
  const bySource = Object.fromEntries(OTHER_KEYS.map(({ key }) => [key, other.byPartySource[key][i]])) as OtherIncome["bySource"];
  return { ...other, bySource, rate: other.byParty[i], covered: 1 };
}

function PartyLive({
  data,
  s,
  other: allOther,
  i,
  catalog,
}: {
  data: Funding;
  s: Schedule;
  other: OtherIncome | null;
  i: number;
  catalog: Map<string, Party>;
}) {
  const p = s.parties[i];
  const name = p.short ?? p.name;
  const reduced = useReducedMotion();
  const [opened] = useState(() => Date.now());
  const [seg, setSeg] = useState(() => segmentAt(s, Date.now()));
  useEffect(() => {
    const id = setInterval(() => setSeg(segmentAt(s, Date.now())), 60_000);
    return () => clearInterval(id);
  }, [s]);
  useEffect(() => {
    document.title = `${name}: javni novac uživo · DOMOVINA Stranke`;
  }, [name]);

  const other = useMemo(() => partyOther(allOther, i), [allOther, i]);
  const n = s.parties.length;

  const stateRef = useRef<HTMLSpanElement>(null);
  const otherRef = useRef<HTMLSpanElement>(null);
  const publicRef = useRef<HTMLSpanElement>(null);
  const srcRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const cumRef = useRef<HTMLSpanElement>(null);
  const leftRef = useRef<HTMLSpanElement>(null);
  const barRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cum0 = new Float64Array(n);
    const cum = new Float64Array(n);
    cumulativeAt(s, opened, cum0);
    const set = (el: HTMLElement | null, v: string) => {
      if (el && el.textContent !== v) el.textContent = v;
    };
    const tick = () => {
      const t = Math.min(Date.now(), s.end);
      cumulativeAt(s, t, cum);
      const session = cum[i] - cum0[i];
      set(stateRef.current, eur(session));
      set(cumRef.current, eur(cum[i]));
      set(leftRef.current, eur(s.totals[i] - cum[i], F0));
      barRef.current?.style.setProperty("transform", `scaleX(${cum[i] / s.totals[i]})`);
      if (other) {
        const elapsed = (Date.now() - opened) / 1000;
        set(otherRef.current, eur(other.rate * elapsed));
        set(publicRef.current, eur(session + other.bySource.local * elapsed));
        OTHER_KEYS.forEach(({ key }, k) => set(srcRefs.current[k], eur(other.bySource[key] * elapsed, F4)));
      }
    };
    tick();
    if (reduced) {
      const id = setInterval(tick, 1000);
      return () => clearInterval(id);
    }
    let raf = 0;
    let last = 0;
    const loop = (now: number) => {
      if (now - last >= 33) {
        last = now;
        tick();
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [s, n, i, opened, reduced, other]);

  const rate = seg ? perSecond(seg, seg.amounts[i]) : 0;
  const stateShare = seg && seg.total ? seg.amounts[i] / seg.total : 0;
  const sh = publicShare(seg, allOther, i);
  const mandates = p.mps_male + p.mps_female;
  const ended = Date.now() >= s.end;
  const path = `/financiranje/uzivo/${liveSlug(p)}`;

  return (
    <section className="container-page py-6 sm:py-10">
      <Link to="/financiranje/uzivo" className="inline-flex items-center gap-1 text-sm text-muted hover:text-navy mb-4">
        <ArrowLeft size={14} /> Sve stranke uživo
      </Link>

      <header className="mb-6 flex items-center gap-4">
        <PartyAvatar size={56} party={catalogAvatar(p, catalog)} />
        <div className="min-w-0">
          <div className="pill mb-1 inline-flex items-center gap-1.5">
            {!ended && (
              <span className="relative flex h-2 w-2">
                {!reduced && <span className="absolute inline-flex h-full w-full rounded-full bg-flag-red opacity-60 animate-ping" />}
                <span className="relative inline-flex h-2 w-2 rounded-full bg-flag-red" />
              </span>
            )}
            {ended ? "11. saziv" : "Uživo · 11. saziv"}
          </div>
          <h1 className="text-2xl sm:text-4xl font-extrabold text-navy leading-tight">{p.name}</h1>
          <div className="text-sm text-muted mt-1">
            {p.independent
              ? "nezavisni zastupnik nacionalne manjine"
              : `${mandates} ${mandates % 10 === 1 && mandates % 100 !== 11 ? "mandat" : "mandata"} (${p.mps_male} M, ${p.mps_female} Ž)`}
            {" · "}
            {F1.format(stateShare * 100)} % novca svih stranaka
            {p.slug && (
              <>
                {" · "}
                <Link to={`/stranka/${p.slug}`}>profil stranke</Link>
              </>
            )}
          </div>
        </div>
      </header>

      <div className={other ? "grid gap-3 lg:grid-cols-2" : ""}>
        <div className="card p-5 sm:p-8 text-center">
          <div className="field-label">Iz državnog proračuna, otkad ste otvorili stranicu</div>
          <div className="text-4xl sm:text-6xl font-extrabold text-flag-red tabular-nums leading-tight my-2">
            <span ref={stateRef} aria-live="off">0,00 €</span>
          </div>
          <div className="text-sm text-muted">
            <strong className="text-navy tabular-nums">{eur(rate, F5)}</strong> u sekundi ·{" "}
            <span className="tabular-nums">{eur(rate * 86400, F0)}</span> na dan
            {seg && <> · {seg.label}</>}
          </div>
          <ShareButton path={path} title={`${name}: javni novac u stvarnom vremenu`} />
        </div>
        {other && <OtherCard other={other} valueRef={otherRef} srcRefs={srcRefs} />}
      </div>

      {other && sh && (
        <PublicCard
          valueRef={publicRef}
          rate={sh.pub}
          share={sh.share}
          year={other.year}
        />
      )}
      {!other && (
        <p className="text-sm text-muted mt-3">
          Za ovog primatelja nema revizije DUR-a za {allOther?.year ?? "zadnju godinu"}, pa ostali prihodi nisu prikazani.
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-3 mt-3">
        <div className="card p-4">
          <div className="field-label">Od {formatDate(data.convocation_start)} do sada</div>
          <div className="text-xl sm:text-2xl font-extrabold text-navy tabular-nums">
            <span ref={cumRef} />
          </div>
          <div className="text-xs text-muted mt-1">iz državnog proračuna u 11. sazivu</div>
        </div>
        <div className="card p-4">
          <div className="field-label">Još do kraja saziva (15. 5. 2028.)</div>
          <div className="text-xl sm:text-2xl font-extrabold text-navy tabular-nums">
            ≈ <span ref={leftRef} />
          </div>
          <div className="text-xs text-muted mt-1">ukupno ≈ {eur(s.totals[i], F0)} za cijeli saziv</div>
        </div>
        <div className="card p-4">
          <div className="field-label">Svi prihodi u sekundi</div>
          <div className="text-xl sm:text-2xl font-extrabold text-navy tabular-nums">
            {eur(sh ? sh.all : rate, F4)}
          </div>
          <div className="text-xs text-muted mt-1">
            {sh ? (
              <>
                {eur(sh.all * 86400 * 365, F0)} godišnje ·{" "}
                <span style={{ color: OTHER }}>drugi izvori {eur(sh.priv, F5)}/s</span>
              </>
            ) : (
              "samo državni proračun (nema revizije)"
            )}
          </div>
        </div>
      </div>

      <div className="card p-4 mt-3">
        <ProgressRow label="Obračunato od novca za cijeli saziv" barRef={barRef} color={NAVY} />
      </div>

      <h2 className="mt-10 mb-2 text-xl font-bold text-navy">Kako se ovo računa</h2>
      <div className="text-sm text-navy-700 max-w-3xl space-y-3 leading-relaxed">
        <p>
          Državni proračun: iznos svakog tromjesečja iz odluka Odbora (a za 2027.
          i 2028. iz zakona i procjene) ravnomjerno raspoređen na sve njegove
          sekunde. Isplata je tromjesečna, pa je ovo obračun, a ne stvarne uplate.
        </p>
        {other && (
          <p>
            Ostali prihodi (lokalni proračuni, članarine, donacije, ostalo) su iz
            revizije Državnog ureda za reviziju za {other.year}., podijeljeni na
            sekunde te godine, uz pretpostavku da teku istom brzinom i danas.
            Javni novac je državni i lokalni proračun zajedno.
          </p>
        )}
        <p>
          Sve stranke i izvori: <Link to="/financiranje/uzivo">Javni novac uživo</Link> ·{" "}
          <Link to="/financiranje">Financiranje stranaka</Link>.
        </p>
      </div>

      <h2 className="mt-10 mb-3 text-xl font-bold text-navy">Ostale stranke uživo</h2>
      <div className="flex flex-wrap gap-2">
        {s.parties.map((q, j) =>
          j === i ? null : (
            <Link key={q.name} to={`/financiranje/uzivo/${liveSlug(q)}`} className="pill hover:text-navy">
              {q.short ?? q.name}
            </Link>
          ),
        )}
      </div>
    </section>
  );
}
