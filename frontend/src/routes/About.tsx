import { Info } from "lucide-react";

export default function About() {
  return (
    <article className="container-page py-10 max-w-3xl">
      <div className="pill mb-3 inline-flex items-center gap-1.5"><Info size={13} /> O projektu</div>
      <h1 className="text-3xl sm:text-4xl font-extrabold text-navy">
        Što je DOMOVINA Stranke
      </h1>
      <p className="lead mt-4 text-lg text-muted leading-relaxed">
        Otvoreni javni katalog svih hrvatskih političkih stranaka — aktivnih i
        ugašenih, od višestranačja 1990. do danas. Cilj je podatke koje
        različiti izvori čuvaju u zatvorenim ili rascjepkanim sustavima učiniti
        dostupnim, pretraživim i izvozim.
      </p>

      <section className="mt-10 prose prose-slate max-w-none">
        <h2 className="text-xl font-bold text-navy">Izvori podataka</h2>
        <ul className="space-y-2 text-navy-700">
          <li>
            <strong>Registar političkih stranaka RH</strong> — službeni registar
            Ministarstva pravosuđa i uprave, preuzet preko{" "}
            <a href="https://data.gov.hr" target="_blank" rel="noopener">
              data.gov.hr
            </a>{" "}
            (OIB, status, adrese, osobe ovlaštene za zastupanje)
          </li>
          <li>
            <strong>NSK — imenik političkih stranaka</strong> — Nacionalna i
            sveučilišna knjižnica: povijesni nazivi, dužnosnici i funkcije s
            mandatima
          </li>
          <li>
            <strong>Nominatim (OpenStreetMap)</strong> — geokodirane koordinate
            sjedišta
          </li>
          <li>
            <strong>DIP — arhiva izbora</strong> — Državno izborno povjerenstvo,
            unakrsna provjera naziva i sudjelovanja na izborima
          </li>
        </ul>

        <h2 className="text-xl font-bold text-navy mt-8">Licenca</h2>
        <p className="text-navy-700">
          Kôd projekta objavljen je pod MIT licencom. Podaci su prikupljeni iz
          javnih izvora i dijele se pod CC-BY licencom — pripisivanje
          "DOMOVINA Stranke" obavezno kod ponovne objave.
        </p>

        <h2 className="text-xl font-bold text-navy mt-8">Tehnologija</h2>
        <p className="text-navy-700">
          Statički React PWA hostan na Cloudflare Pages. Sve podatke fetcha
          klijent iz pre-generiranih JSON datoteka — bez backenda, bez
          praćenja, bez kolačića.
        </p>

        <h2 className="text-xl font-bold text-navy mt-8">Sestrinski projekt</h2>
        <p className="text-navy-700">
          Katalog hrvatskih nogometnih klubova živi na{" "}
          <a href="https://klubovi.domovina.ai" target="_blank" rel="noopener">
            klubovi.domovina.ai
          </a>
          .
        </p>

        <h2 className="text-xl font-bold text-navy mt-8">Doprinos</h2>
        <p className="text-navy-700">
          Pogreška u podacima? Nedostaje stranka? Otvori issue na{" "}
          <a
            href="https://github.com/domovinatv/stranke.domovina.ai"
            target="_blank"
            rel="noopener"
          >
            github.com/domovinatv/stranke.domovina.ai
          </a>{" "}
          ili javi se na{" "}
          <a href="mailto:hello@domovina.ai">hello@domovina.ai</a>.
        </p>
      </section>
    </article>
  );
}
