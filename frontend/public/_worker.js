/**
 * Cloudflare Pages Advanced Mode worker — stranke.domovina.ai
 *
 * Odgovornosti:
 *  1. SPA fallback — sve neasset rute vraćaju index.html
 *  2. OG/social tagovi — za /stranka/<slug> obogati index.html s meta tagovima
 *     iz parties.json prije nego što crawler dobije odgovor
 *  3. Cache-Control — patchamo u workeru jer _headers nije aktivan dok worker
 *     handla request (CF Pages Advanced Mode contract)
 *
 * NAPOMENA: bez _redirects fajla — ako se vrati SPA fallback unutra, ASSETS.fetch
 * vraća index.html za bilo koji nepostojeći /stranka/* prije nego worker stigne
 * injekciju OG-a.
 */

const SITE = "https://stranke.domovina.ai";

let PARTIES_PROMISE = null;

async function loadParties(env) {
  if (PARTIES_PROMISE) return PARTIES_PROMISE;
  PARTIES_PROMISE = env.ASSETS.fetch(new Request(`${SITE}/data/parties.json`))
    .then((r) => (r.ok ? r.json() : []))
    .catch(() => []);
  return PARTIES_PROMISE;
}

function applyCacheHeaders(res, path) {
  const headers = new Headers(res.headers);
  if (/^\/(sw\.js|registerSW\.js|manifest\.webmanifest)$/.test(path)) {
    // Service worker mora odmah vidjeti novi deploy: inače Cloudflare (.js se
    // cacheira na rubu) satima vraća stari sw.js koji poslužuje stari bundle.
    headers.set("Cache-Control", "no-cache, no-store, must-revalidate");
  } else if (/^\/assets\//.test(path)) {
    headers.set("Cache-Control", "public, max-age=31536000, immutable");
  } else if (/^\/data\//.test(path)) {
    headers.set("Cache-Control", "public, max-age=3600, must-revalidate");
  } else if (/^\/icons\//.test(path) || path === "/og-image.png") {
    headers.set("Cache-Control", "public, max-age=86400");
  } else if (/\.(js|css|svg|woff2?|png|jpg|webp)$/.test(path)) {
    headers.set("Cache-Control", "public, max-age=3600");
  }
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  headers.set("Permissions-Policy", "interest-cohort=()");
  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers,
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) =>
    ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[ch],
  );
}

function statusLabel(party) {
  if (party.status === "AKTIVAN") return "aktivna stranka";
  if (party.status === "PRESTANAK") return "ugašena stranka";
  return null;
}

function buildOgFor(party, url) {
  const title = `${party.canonical_name} · DOMOVINA Stranke`;
  const parts = [];
  const st = statusLabel(party);
  if (st) parts.push(st);
  if (party.city) parts.push(party.city);
  if (party.county) parts.push(party.county.replace(" županija", ""));
  if (party.founded_date) {
    parts.push(`osnovana ${party.founded_date.slice(0, 4)}.`);
  } else if (party.registered_at) {
    parts.push(`registrirana ${party.registered_at.slice(0, 4)}.`);
  }
  if (party.president) parts.push(`predsjednik ${party.president}`);
  const desc =
    parts.length > 0
      ? `${parts.join(" · ")}. Kontakti i podaci na stranke.domovina.ai.`
      : `Podaci o stranci ${party.canonical_name} na stranke.domovina.ai.`;
  const image = `${SITE}/og-image.png`;
  return { title, desc, image, canonical: url };
}

class OgRewriter {
  constructor(og) {
    this.og = og;
    this.seen = new Set();
  }
  element(el) {
    const name = el.tagName.toLowerCase();
    if (name === "title") {
      el.setInnerContent(this.og.title);
      return;
    }
    if (name !== "meta" && name !== "link") return;
    const property = el.getAttribute("property") || "";
    const metaName = el.getAttribute("name") || "";
    const rel = el.getAttribute("rel") || "";
    const map = {
      "og:title": this.og.title,
      "og:description": this.og.desc,
      "og:image": this.og.image,
      "og:url": this.og.canonical,
      "twitter:title": this.og.title,
      "twitter:description": this.og.desc,
      "twitter:image": this.og.image,
    };
    if (property) this.seen.add(property);
    if (property && map[property] != null) {
      el.setAttribute("content", map[property]);
    }
    if (metaName === "description") {
      el.setAttribute("content", this.og.desc);
    }
    if (metaName === "twitter:card") {
      el.setAttribute("content", "summary_large_image");
    }
    if (rel === "canonical") {
      el.setAttribute("href", this.og.canonical);
    }
  }
}

class HeadInjector {
  constructor(rewriter, extras) {
    this.r = rewriter;
    this.extras = extras;
  }
  element(el) {
    if (el.tagName.toLowerCase() !== "head") return;
    // Append any og:* properties that the source index.html did not have so
    // crawlers see a complete set. Runs at </head>: only then has the
    // rewriter seen the existing <meta> tags.
    el.onEndTag((end) => {
      for (const [prop, val] of Object.entries(this.extras)) {
        if (this.r.seen.has(prop)) continue;
        end.before(`<meta property="${prop}" content="${escapeHtml(val)}" />`, { html: true });
      }
    });
  }
}

const fmtEur = (n, digits = 2) =>
  new Intl.NumberFormat("hr-HR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);

async function buildFundingOg(env) {
  const fallback = {
    title: "Koliko stranke dobivaju iz proračuna · DOMOVINA Stranke",
    desc: "Iznos po stranci i po zastupniku u 11. sazivu Hrvatskoga sabora, prema odlukama objavljenima u Narodnim novinama.",
    image: `${SITE}/og-image.png`,
    canonical: `${SITE}/financiranje`,
  };
  try {
    const r = await env.ASSETS.fetch(new Request(`${SITE}/data/financiranje.json`));
    if (!r.ok) return fallback;
    const d = await r.json();
    const cur = d.rates[d.rates.length - 1];
    return {
      ...fallback,
      desc:
        `${fmtEur(d.totals.received_eur / 1e6)} mil. € od 16. 5. 2024. · ` +
        `${fmtEur(cur.month_m)} € mjesečno po zastupniku, ${fmtEur(cur.month_f)} € po zastupnici (${d.year}.). ` +
        `Iznos po stranci i po osobi, iz odluka u Narodnim novinama.`,
    };
  } catch {
    return fallback;
  }
}

/** € u sekundi svim strankama u tromjesečju koje je u tijeku (kao na /financiranje/uzivo). */
function livePeriod(d, now = Date.now()) {
  const day = (iso) => Date.parse(iso + "T00:00:00+01:00");
  const p = d.periods.find((x) => day(x.from) <= now && now < day(x.to) + 86400000) ?? d.periods[d.periods.length - 1];
  const total = d.parties.reduce((s, party) => s + (party.by_period[p.label] || 0), 0);
  return { p, total, rate: total / ((day(p.to) + 86400000 - day(p.from)) / 1000) };
}

async function buildFundingLiveOg(env) {
  const fallback = {
    title: "Javni novac u stvarnom vremenu · DOMOVINA Stranke",
    desc: "Koliko parlamentarnim strankama svake sekunde pripada iz državnog proračuna, uživo, prema odlukama u Narodnim novinama.",
    image: `${SITE}/og-image.png`,
    canonical: `${SITE}/financiranje/uzivo`,
  };
  try {
    const r = await env.ASSETS.fetch(new Request(`${SITE}/data/financiranje.json`));
    if (!r.ok) return fallback;
    const d = await r.json();
    const { p, total, rate } = livePeriod(d);
    const hdz = d.parties[0];
    const share = (hdz.by_period[p.label] || 0) / total;
    return {
      ...fallback,
      desc:
        `Svake sekunde strankama iz proračuna pripada ${fmtEur(rate)} €, ${fmtEur(rate * 86400, 0)} € na dan ` +
        `(${hdz.short || hdz.name} ${fmtEur(rate * share, 3)} €/s). ` +
        `Do kraja 11. saziva (15. 5. 2028.) ≈ ${fmtEur(d.projection.saziv_total_eur / 1e6)} mil. €. Brojači uživo.`,
    };
  } catch {
    return fallback;
  }
}

async function serveSpaWithOg(env, og) {
  const indexRes = await env.ASSETS.fetch(new Request(`${SITE}/index.html`));
  if (!indexRes.ok) return indexRes;

  const rewriter = new OgRewriter(og);

  const transformed = new HTMLRewriter()
    .on("title", rewriter)
    .on("meta", rewriter)
    .on("link", rewriter)
    .on("head", new HeadInjector(rewriter, {
      "og:title": og.title,
      "og:description": og.desc,
      "og:image": og.image,
      "og:url": og.canonical,
      "og:type": "website",
      "og:locale": "hr_HR",
    }))
    .transform(indexRes);

  const out = new Response(transformed.body, transformed);
  out.headers.set("Content-Type", "text/html; charset=utf-8");
  out.headers.set("Cache-Control", HTML_CACHE);
  out.headers.set("X-Content-Type-Options", "nosniff");
  out.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  return out;
}

// HTML se uvijek provjerava: service worker ga precachea, a da je HTTP-cachiran
// (prije max-age=300), novi sw.js bi spremio stari index.html sa starim bundleom.
const HTML_CACHE = "no-cache";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // Pages bi /index.html preusmjerio (308) na /, a service worker precachea
    // baš /index.html; poslužimo ga izravno i bez cachea.
    if (path === "/index.html") {
      const indexRes = await env.ASSETS.fetch(new Request(`${SITE}/`));
      const headers = new Headers(indexRes.headers);
      headers.set("Cache-Control", HTML_CACHE);
      headers.set("Content-Type", "text/html; charset=utf-8");
      return new Response(indexRes.body, { status: 200, headers });
    }

    // Static assets — pass through to ASSETS with cache patching.
    if (/\.\w{1,8}$/.test(path)) {
      const res = await env.ASSETS.fetch(request);
      return applyCacheHeaders(res, path);
    }

    // OG injection for /stranka/<slug>
    const m = path.match(/^\/stranka\/([^/]+)\/?$/);
    if (m) {
      const slug = decodeURIComponent(m[1]);
      const parties = await loadParties(env);
      const party = parties.find((p) => p.slug === slug);
      if (party) {
        return serveSpaWithOg(env, buildOgFor(party, `${SITE}${path}`));
      }
    }

    if (/^\/financiranje\/uzivo\/?$/.test(path)) {
      return serveSpaWithOg(env, await buildFundingLiveOg(env));
    }

    if (/^\/financiranje\/?$/.test(path)) {
      return serveSpaWithOg(env, await buildFundingOg(env));
    }

    // SPA fallback — serve index.html for everything else
    const indexRes = await env.ASSETS.fetch(new Request(`${SITE}/index.html`));
    const headers = new Headers(indexRes.headers);
    headers.set("Cache-Control", HTML_CACHE);
    headers.set("Content-Type", "text/html; charset=utf-8");
    headers.set("X-Content-Type-Options", "nosniff");
    return new Response(indexRes.body, {
      status: indexRes.status === 404 ? 200 : indexRes.status,
      headers,
    });
  },
};
