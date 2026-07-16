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
  if (/^\/assets\//.test(path)) {
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
    if (property && map[property] != null) {
      el.setAttribute("content", map[property]);
      this.seen.add(property);
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
    // crawlers see a complete set.
    for (const [prop, val] of Object.entries(this.extras)) {
      if (this.r.seen.has(prop)) continue;
      const v = escapeHtml(val);
      el.append(
        `<meta property="${prop}" content="${v}" />`,
        { html: true },
      );
    }
  }
}

async function serveSpaWithOg(env, request, party) {
  const url = new URL(request.url);
  const indexRes = await env.ASSETS.fetch(new Request(`${SITE}/index.html`));
  if (!indexRes.ok) return indexRes;

  const og = buildOgFor(party, `${SITE}${url.pathname}`);
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
  out.headers.set("Cache-Control", "public, max-age=300, must-revalidate");
  out.headers.set("X-Content-Type-Options", "nosniff");
  out.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  return out;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

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
        return serveSpaWithOg(env, request, party);
      }
    }

    // SPA fallback — serve index.html for everything else
    const indexRes = await env.ASSETS.fetch(new Request(`${SITE}/index.html`));
    const headers = new Headers(indexRes.headers);
    headers.set("Cache-Control", "public, max-age=300, must-revalidate");
    headers.set("Content-Type", "text/html; charset=utf-8");
    headers.set("X-Content-Type-Options", "nosniff");
    return new Response(indexRes.body, {
      status: indexRes.status === 404 ? 200 : indexRes.status,
      headers,
    });
  },
};
