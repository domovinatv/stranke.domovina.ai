import { ArrowLeft, Check, Radio, Share2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { formatDate, loadFunding, loadParties } from "@/lib/data";
import type { Funding, Party } from "@/lib/types";
import {
  buildSchedule,
  catalogAvatar,
  cumulativeAt,
  perSecond,
  segmentAt,
  type Schedule,
  type Segment,
} from "@/lib/fundingLive";
import { PageSpinner } from "@/components/PageSpinner";
import { PartyAvatar } from "@/components/PartyAvatar";

const MALE = "#002F6C";
const FEMALE = "#DB2777";

const nf = (digits: number) =>
  new Intl.NumberFormat("hr-HR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const F0 = nf(0);
const F2 = nf(2);
const F4 = nf(4);
const F5 = nf(5);
const eur = (n: number, f = F2) => f.format(n) + " €";
const mil = (n: number) => nf(2).format(n / 1e6) + " mil. €";

const SOURCE_TEXT: Record<Segment["source"], string> = {
  odluka: "odluka Odbora",
  zakon: "izračun po zakonu",
  procjena: "procjena",
};

function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

export default function FundingLiveRoute() {
  const [data, setData] = useState<Funding | null>(null);
  const [catalog, setCatalog] = useState<Map<string, Party>>(new Map());

  useEffect(() => {
    document.title = "Javni novac uživo · DOMOVINA Stranke";
    loadFunding().then(setData);
    loadParties()
      .then((ps) => setCatalog(new Map(ps.map((p) => [p.slug, p]))))
      .catch(() => undefined);
  }, []);

  const schedule = useMemo(() => (data ? buildSchedule(data) : null), [data]);
  if (!data || !schedule) return <PageSpinner />;
  return <Live data={data} s={schedule} catalog={catalog} />;
}

function Live({ data, s, catalog }: { data: Funding; s: Schedule; catalog: Map<string, Party> }) {
  const reduced = useReducedMotion();
  const [opened] = useState(() => Date.now());
  // Razdoblje se mijenja najviše jednom u tromjesečju; dovoljno ga je
  // provjeravati svake minute (stope u tekstu, oznaka izvora).
  const [seg, setSeg] = useState(() => segmentAt(s, Date.now()));
  useEffect(() => {
    const id = setInterval(() => setSeg(segmentAt(s, Date.now())), 60_000);
    return () => clearInterval(id);
  }, [s]);

  const n = s.parties.length;
  const max = Math.max(...s.totals);

  // Čvorovi koje petlja ažurira izravno, bez React re-rendera.
  const heroRef = useRef<HTMLSpanElement>(null);
  const cumRef = useRef<HTMLSpanElement>(null);
  const leftRef = useRef<HTMLSpanElement>(null);
  const clockRef = useRef<HTMLSpanElement>(null);
  const timeBarRef = useRef<HTMLDivElement>(null);
  const moneyBarRef = useRef<HTMLDivElement>(null);
  const seatMRef = useRef<HTMLSpanElement>(null);
  const seatFRef = useRef<HTMLSpanElement>(null);
  const rowSession = useRef<(HTMLSpanElement | null)[]>([]);
  const rowCum = useRef<(HTMLSpanElement | null)[]>([]);
  const rowBar = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    const cum0 = new Float64Array(n);
    const cum = new Float64Array(n);
    const total0 = cumulativeAt(s, opened, cum0);
    const set = (el: HTMLElement | null, v: string) => {
      if (el && el.textContent !== v) el.textContent = v;
    };

    const tick = () => {
      const t = Math.min(Date.now(), s.end);
      const total = cumulativeAt(s, t, cum);
      const session = total - total0;
      set(heroRef.current, eur(session));
      set(cumRef.current, eur(total));
      set(leftRef.current, eur(s.total - total, F0));
      const timeFrac = (t - s.start) / (s.end - s.start);
      timeBarRef.current?.style.setProperty("transform", `scaleX(${timeFrac})`);
      moneyBarRef.current?.style.setProperty("transform", `scaleX(${total / s.total})`);

      let secs = Math.max(0, Math.floor((s.end - Date.now()) / 1000));
      const d = Math.floor(secs / 86400);
      secs -= d * 86400;
      const hh = String(Math.floor(secs / 3600)).padStart(2, "0");
      const mm = String(Math.floor((secs % 3600) / 60)).padStart(2, "0");
      const ss = String(secs % 60).padStart(2, "0");
      set(clockRef.current, `${F0.format(d)} d ${hh}:${mm}:${ss}`);

      const cur = segmentAt(s, t);
      if (cur) {
        const elapsed = (t - opened) / 1000;
        const seatM = perSecond(cur, cur.total / cur.weight);
        set(seatMRef.current, eur(seatM * elapsed, F4));
        set(seatFRef.current, eur(seatM * 1.1 * elapsed, F4));
      }

      for (let i = 0; i < n; i++) {
        set(rowSession.current[i], "+" + eur(cum[i] - cum0[i], F4));
        set(rowCum.current[i], eur(cum[i]));
        rowBar.current[i]?.style.setProperty("transform", `scaleX(${cum[i] / max})`);
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
      // ~30 sličica u sekundi je dovoljno za brojače, a štedi bateriju.
      if (now - last >= 33) {
        last = now;
        tick();
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [s, n, max, opened, reduced]);

  const rate = seg ? perSecond(seg, seg.total) : 0;
  const seatM = seg ? perSecond(seg, seg.total / seg.weight) : 0;
  const lastDecided = [...s.segments].reverse().find((x) => x.source === "odluka");
  const y28 = data.projection.years.find((y) => y.tax_kind !== "ostvareno");
  const ended = Date.now() >= s.end;

  return (
    <section className="container-page py-6 sm:py-10">
      <Link to="/financiranje" className="inline-flex items-center gap-1 text-sm text-muted hover:text-navy mb-4">
        <ArrowLeft size={14} /> Financiranje stranaka
      </Link>

      <header className="mb-6">
        <div className="pill mb-2 inline-flex items-center gap-1.5">
          {ended ? (
            <Radio size={13} />
          ) : (
            <span className="relative flex h-2 w-2">
              {!reduced && <span className="absolute inline-flex h-full w-full rounded-full bg-flag-red opacity-60 animate-ping" />}
              <span className="relative inline-flex h-2 w-2 rounded-full bg-flag-red" />
            </span>
          )}
          {ended ? "11. saziv Hrvatskoga sabora" : "Uživo · 11. saziv Hrvatskoga sabora"}
        </div>
        <h1 className="text-2xl sm:text-4xl font-extrabold text-navy max-w-3xl leading-tight">
          Javni novac u stvarnom vremenu
        </h1>
        <p className="text-muted mt-3 max-w-2xl leading-relaxed">
          Parlamentarne stranke iz državnog proračuna dobivaju novac za svaki
          saborski mandat. Ovdje se taj iznos raspoređuje po sekundama: dok
          gledate stranicu, vidite koliko je kojoj stranci pripalo.
        </p>
      </header>

      <div className="card p-5 sm:p-8 text-center">
        <div className="field-label">Otkad ste otvorili ovu stranicu, strankama je pripalo</div>
        <div className="text-4xl sm:text-6xl font-extrabold text-flag-red tabular-nums leading-tight my-2">
          <span ref={heroRef} aria-live="off">0,00 €</span>
        </div>
        <div className="text-sm text-muted">
          {ended ? (
            "11. saziv je završio 15. 5. 2028."
          ) : (
            <>
              <strong className="text-navy tabular-nums">{eur(rate, F4)}</strong> u sekundi ·{" "}
              <span className="tabular-nums">{eur(rate * 86400, F0)}</span> na dan ·{" "}
              {seg && <>{SOURCE_TEXT[seg.source]}{seg.nn ? ` NN ${seg.nn}` : ""}, {seg.label}</>}
            </>
          )}
        </div>
        <ShareButton />
      </div>

      <div className="grid gap-3 sm:grid-cols-3 mt-3">
        <div className="card p-4">
          <div className="field-label">Od {formatDate(data.convocation_start)} do sada</div>
          <div className="text-xl sm:text-2xl font-extrabold text-navy tabular-nums">
            <span ref={cumRef} />
          </div>
          <div className="text-xs text-muted mt-1">obračunato svim strankama u 11. sazivu</div>
        </div>
        <div className="card p-4">
          <div className="field-label">Do kraja saziva (15. 5. 2028.)</div>
          <div className="text-xl sm:text-2xl font-extrabold text-navy tabular-nums">
            <span ref={clockRef} />
          </div>
          <div className="text-xs text-muted mt-1">redovni kraj četverogodišnjeg mandata</div>
        </div>
        <div className="card p-4">
          <div className="field-label">Još do kraja saziva</div>
          <div className="text-xl sm:text-2xl font-extrabold text-navy tabular-nums">
            ≈ <span ref={leftRef} />
          </div>
          <div className="text-xs text-muted mt-1">
            ukupno ≈ {mil(s.total)} za cijeli saziv; 2028. je procjena
          </div>
        </div>
      </div>

      <div className="card p-4 mt-3">
        <div className="grid gap-3 text-sm">
          <ProgressRow label="Proteklo vrijeme saziva" barRef={timeBarRef} color="#7099C6" />
          <ProgressRow label="Obračunati novac saziva" barRef={moneyBarRef} color={MALE} />
        </div>
        <p className="text-xs text-muted mt-3">
          Novac zaostaje za vremenom jer iznos po mandatu raste svake godine
          (0,075 % poreznih prihoda od prije dvije godine).
        </p>
      </div>

      <div className="card p-4 sm:p-5 mt-3">
        <div className="field-label">Jedan mandat</div>
        <div className="grid gap-4 sm:grid-cols-2">
          <SeatTile
            who="zastupnik"
            color={MALE}
            rate={seatM}
            valueRef={seatMRef}
          />
          <SeatTile
            who="zastupnica"
            color={FEMALE}
            rate={seatM * 1.1}
            valueRef={seatFRef}
            note="+10 % za podzastupljeni spol (čl. 9.)"
          />
        </div>
      </div>

      <h2 className="mt-10 mb-1 text-xl font-bold text-navy">Po strankama, uživo</h2>
      <p className="text-sm text-muted mb-4 max-w-3xl">
        Puna traka je obračunato od {formatDate(data.convocation_start)} do ovog
        trenutka, svijetla je iznos do kraja saziva. Sve trake na istoj su
        skali (najveći iznos je HDZ-ov za cijeli saziv).
      </p>
      <ol className="card divide-y divide-border">
        {s.parties.map((p, i) => {
          const r = seg ? perSecond(seg, seg.amounts[i]) : 0;
          const mandates = p.mps_male + p.mps_female;
          return (
            <li key={p.name} className="p-3 sm:px-4">
              <div className="flex items-start gap-3">
                <span className="w-5 pt-1.5 text-right text-xs text-muted tabular-nums">{i + 1}.</span>
                <PartyAvatar size={28} party={catalogAvatar(p, catalog)} />
                <div className="min-w-0 flex-1 sm:flex sm:items-center sm:gap-3">
                  <div className="min-w-0 sm:flex-1">
                    <div className="font-semibold text-navy leading-snug sm:truncate">
                      {p.slug ? <Link to={`/stranka/${p.slug}`}>{p.name}</Link> : p.name}
                    </div>
                    <div className="text-xs text-muted">
                      {p.independent ? "nezavisni zastupnik nacionalne manjine" : `${mandates} ${mandates % 10 === 1 && mandates % 100 !== 11 ? "mandat" : "mandata"}`} ·{" "}
                      <span className="tabular-nums">{eur(r, F5)}/s</span>
                    </div>
                  </div>
                  <div className="mt-1 flex items-baseline justify-between gap-3 sm:mt-0 sm:block sm:text-right sm:shrink-0">
                    <div className="text-sm font-bold text-navy tabular-nums">
                      <span ref={(el) => (rowCum.current[i] = el)} />
                    </div>
                    <div className="text-xs text-flag-red tabular-nums">
                      <span ref={(el) => (rowSession.current[i] = el)} />
                    </div>
                  </div>
                </div>
              </div>
              <div className="relative mt-2 ml-8 h-2 rounded-full bg-surface overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{ width: `${(100 * s.totals[i]) / max}%`, background: "#D5E0EF" }}
                />
                <div
                  ref={(el) => (rowBar.current[i] = el)}
                  className="absolute inset-y-0 left-0 w-full origin-left rounded-full"
                  style={{ background: MALE, transform: "scaleX(0)" }}
                />
              </div>
            </li>
          );
        })}
      </ol>
      <p className="text-xs text-muted mt-2">
        Gornji broj: obračunato od {formatDate(data.convocation_start)}. Crveni
        broj: otkad gledate stranicu.
      </p>

      <h2 className="mt-10 mb-2 text-xl font-bold text-navy">Kako se ovo računa</h2>
      <div className="text-sm text-navy-700 max-w-3xl space-y-3 leading-relaxed">
        <p>
          Zakon o financiranju političkih aktivnosti (čl. 10.) propisuje isplatu{" "}
          <strong>tromjesečno, u jednakim iznosima</strong>. Novac dakle ne
          stiže na račune svake sekunde: ovdje je iznos svakog tromjesečja
          ravnomjerno raspoređen na sve njegove sekunde. Brojač prikazuje
          obračun, a ne stvarne uplate.
        </p>
        <p>
          Iznosi do {lastDecided ? lastDecided.label : "danas"} su iz odluka
          Odbora za Ustav, Poslovnik i politički sustav (zadnja{" "}
          {lastDecided?.nn && <>NN {lastDecided.nn}</>}). Za 2027. iznos je već
          određen zakonom: 0,075 % poreznih prihoda ostvarenih 2025., ukupno{" "}
          {eur(data.projection.years.find((y) => y.year === 2027)?.annual_eur ?? 0)}; raspodjela
          po mandatima pretpostavlja današnji omjer zastupnika i zastupnica.
          {y28 && (
            <>
              {" "}Za 2028. (do 15. 5.) iznos je <strong>procjena</strong> prema
              planu poreznih prihoda za 2026.; prava brojka bit će poznata kad
              se objavi izvještaj o izvršenju proračuna za 2026. (ljeto 2027.).
              Po trendu prvog polugodišta 2026. bilo bi ≈{" "}
              {mil(data.projection.saziv_total_alt_eur)} za cijeli saziv umjesto{" "}
              {mil(data.projection.saziv_total_eur)}.
            </>
          )}
        </p>
        <p>
          Granice razdoblja su u ponoć po hrvatskom vremenu. Novac za mandat
          ide stranci s čije je liste zastupnik izabran, i kad je on u
          međuvremenu iz nje izašao (čl. 7.).
          Izvori, odluke i provjera prema Saborovim izvješćima su na stranici{" "}
          <Link to="/financiranje">Financiranje stranaka</Link>.
        </p>
      </div>
    </section>
  );
}

function ProgressRow({
  label,
  barRef,
  color,
}: {
  label: string;
  barRef: React.RefObject<HTMLDivElement>;
  color: string;
}) {
  return (
    <div>
      <div className="text-xs text-muted mb-1">{label}</div>
      <div className="relative h-2.5 rounded-full bg-surface overflow-hidden">
        <div
          ref={barRef}
          className="absolute inset-0 origin-left rounded-full"
          style={{ background: color, transform: "scaleX(0)" }}
        />
      </div>
    </div>
  );
}

function SeatTile({
  who,
  color,
  rate,
  valueRef,
  note,
}: {
  who: string;
  color: string;
  rate: number;
  valueRef: React.RefObject<HTMLSpanElement>;
  note?: string;
}) {
  return (
    <div>
      <div className="text-sm text-navy-700">
        Mandat jednog {who === "zastupnik" ? "zastupnika" : "zastupnice"} stranci donosi
      </div>
      <div className="text-2xl font-extrabold tabular-nums" style={{ color }}>
        {eur(rate, F5)} <span className="text-base font-semibold">u sekundi</span>
      </div>
      <div className="text-xs text-muted">
        {eur(rate * 86400)} na dan · otkad gledate:{" "}
        <span ref={valueRef} className="tabular-nums" />
        {note && <> · {note}</>}
      </div>
    </div>
  );
}

function ShareButton() {
  const [copied, setCopied] = useState(false);
  const share = async () => {
    const url = window.location.origin + "/financiranje/uzivo";
    const title = "Javni novac u stvarnom vremenu";
    try {
      if (navigator.share) {
        await navigator.share({ title, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* korisnik odustao */
    }
  };
  return (
    <button type="button" onClick={share} className="btn-ghost mt-4">
      {copied ? <Check size={14} /> : <Share2 size={14} />}
      {copied ? "Poveznica kopirana" : "Podijeli"}
    </button>
  );
}
