"""Kompas stranaka: fetch party programmes (izborni 2024, koalicijski, trajni).

Scope is data/kompas/liste_2024.json → stranke[] (+ manjine[]). Which URL is a
programme is decided by a person and recorded in data/kompas/programi_izvori.json
(per party / coalition / minority list: sources, the corrected website, and the
URLs checked when nothing was found). This script:

  default      fetches every curated source (direct; Wayback snapshot when the
               page is gone or the source says so; Firecrawl rawHtml when the
               site blocks plain clients), keeps the original under
               data/raw/programi/<slug>/<sha256[:12]>.<ext>, measures it
               (format, PDF pages, word count) and writes data/kompas/programi.json
  --discover   collects candidates for review: programme-looking links on the
               party website, PDFs the Wayback CDX saw on that domain in
               2023–2024, and Firecrawl search results → data/raw/programi/
               _discovery/<slug>.json (nothing is accepted automatically)

Every HTTP response and Firecrawl call is cached, so a warm re-run makes no
network calls and leaves programi.json byte-identical. --offline turns a cache
miss into an error. Firecrawl budget: --fc-per-party (12) and --fc-total (450);
on InsufficientCreditsError the run stops fetching from Firecrawl, writes what
it has and says so. No LLM calls.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.firecrawl import InsufficientCreditsError  # noqa: E402
from src.kompas import programi as P  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("programi")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pypdf").setLevel(logging.ERROR)

DISCOVERY_DIR = P.RAW_DIR / "_discovery"


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


class Runner:
    def __init__(self, args):
        self.args = args
        self.fetcher = P.Fetcher(offline=args.offline)
        self.fc = P.FirecrawlBudget(self._fc_client, per_party=args.fc_per_party,
                                    total=args.fc_total, offline=args.offline)
        self.fc_stopped: str | None = None

    @staticmethod
    def _fc_client():
        from src.firecrawl import FirecrawlClient
        return FirecrawlClient()

    # ------------------------------------------------------------- fetching

    def fetch(self, src: dict) -> P.Fetched | None:
        """Bytes for one curated source, trying web → wayback → firecrawl."""
        url = src["url"]
        order = src.get("izvor_redoslijed") or ["web", "wayback", "firecrawl"]
        for how in order:
            try:
                got = getattr(self, f"_via_{how}")(src)
            except P.OfflineMiss as e:
                log.error("offline, nije u cacheu: %s", e)
                got = None
            if got is not None:
                return got
        log.warning("nijedan izvor nije dao dokument: %s", url)
        return None

    def _usable(self, r: P.Response, src: dict) -> bool:
        if not r.ok:
            return False
        if src.get("ocekuj_pdf") and not P.is_pdf(r.body):
            return False
        return True

    def _via_web(self, src):
        r = self.fetcher.get(src["url"])
        if not self._usable(r, src):
            return None
        return P.Fetched(r.body, "web", src["url"], None, None, r.fetched_at)

    def _via_wayback(self, src):
        ts = src.get("wayback_ts", P.WAYBACK_TS_2024)
        r = self.fetcher.get(P.wayback_raw_url(src["url"], ts))
        if not self._usable(r, src):
            return None
        view = P.wayback_view_url(r.final_url) or P.wayback_view_url(P.wayback_raw_url(src["url"], ts))
        return P.Fetched(r.body, "wayback", src["url"], view, P.wayback_date(r.final_url),
                         r.fetched_at)

    def _via_firecrawl(self, src):
        if self.fc_stopped:
            return None
        try:
            html = self.fc.scrape_html(src.get("_owner", "?"), src["url"])
        except InsufficientCreditsError as e:
            self.fc_stopped = f"InsufficientCreditsError: {e}"
            log.error("Firecrawl: nema kredita, nastavljam bez njega")
            return None
        except P.BudgetExceeded as e:
            log.warning("Firecrawl budžet: %s", e)
            return None
        except RuntimeError as e:
            log.warning("Firecrawl scrape %s: %s", src["url"], e)
            return None
        if not html:
            return None
        meta_p = P.HTTP_DIR / f"fc-{P._key(src['url'])}.json"
        if meta_p.exists():
            fetched_at = load_json(meta_p)["fetched_at"]
        else:
            fetched_at = P.now_iso()
            meta_p.parent.mkdir(parents=True, exist_ok=True)
            meta_p.write_text(json.dumps({"url": src["url"], "fetched_at": fetched_at}),
                              encoding="utf-8")
        return P.Fetched(html.encode("utf-8"), "firecrawl", src["url"], None, None, fetched_at)

    @staticmethod
    def store(slug: str, sha: str, ext: str, body: bytes) -> None:
        p = P.raw_path(slug, sha, ext)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)

    # ------------------------------------------------------------- discovery

    def discover(self, party: dict, entry: dict) -> dict:
        slug = party["slug"]
        site = entry.get("web", party.get("website"))
        rep: dict = {"slug": slug, "web": site, "linkovi": [], "cdx": [], "pretraga": []}
        if site:
            home = self.fetcher.get(site)
            rep["web_status"] = home.status or home.error
            if home.ok:
                links = P.programme_links(home.body, home.final_url)
                rep["linkovi"] = [{"url": u, "tekst": t} for u, t in links]
                for u, _t in links[:6]:
                    if urlparse(u).netloc != urlparse(home.final_url).netloc or u.lower().endswith(".pdf"):
                        continue
                    sub = self.fetcher.get(u)
                    if sub.ok and not P.is_pdf(sub.body):
                        for su, st in P.programme_links(sub.body, sub.final_url):
                            if su.lower().endswith(".pdf") or "program" in su.lower():
                                rep["linkovi"].append({"url": su, "tekst": st, "sa": u})
            dom = urlparse(site if "//" in site else "http://" + site).netloc
            dom = dom.removeprefix("www.")
            for frm, to in (("2023", "2024"), ("2019", "2026")):
                r = self.fetcher.get(P.cdx_url(dom, frm, to))
                rows = P.parse_cdx(r.body) if r.ok else []
                for row in rows:
                    if P.PROGRAM_HINT.search(row.get("original", "")):
                        rep["cdx"].append({"url": row["original"], "ts": row["timestamp"],
                                           "raspon": f"{frm}-{to}"})
        name = party.get("short_name") or party["canonical_name"]
        queries = entry.get("upiti") or [f'{name} izborni program 2024 parlamentarni izbori',
                                         f'{name} program stranke']
        for q in queries:
            try:
                for hit in self.fc.search(slug, q):
                    rep["pretraga"].append({"upit": q, "url": hit.get("url"),
                                            "naslov": hit.get("title"),
                                            "opis": (hit.get("description") or "")[:200]})
            except InsufficientCreditsError as e:
                self.fc_stopped = str(e)
                break
            except (P.BudgetExceeded, P.OfflineMiss, RuntimeError) as e:
                rep.setdefault("greske", []).append(str(e)[:200])
        DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
        (DISCOVERY_DIR / f"{slug}.json").write_text(P.dump(rep), encoding="utf-8")
        return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", help="slug of one party (or list_id / manjine_id)")
    ap.add_argument("--offline", action="store_true", help="cache only; a miss is an error")
    ap.add_argument("--discover", action="store_true", help="collect candidates for review")
    ap.add_argument("--fc-per-party", type=int, default=12)
    ap.add_argument("--fc-total", type=int, default=450)
    ap.add_argument("--liste", type=Path, default=P.LISTE_PATH)
    ap.add_argument("--izvori", type=Path, default=P.IZVORI_PATH)
    ap.add_argument("--out", type=Path, default=P.OUT_PATH)
    args = ap.parse_args()

    liste = load_json(args.liste)
    izvori = load_json(args.izvori)
    run = Runner(args)

    try:
        if args.discover:
            for party in sorted(liste["stranke"], key=lambda s: s["slug"]):
                if args.only and party["slug"] != args.only:
                    continue
                rep = run.discover(party, izvori.get("stranke", {}).get(party["slug"], {}))
                log.info("%-45s linkova %2d, cdx %2d, pretraga %2d", party["slug"],
                         len(rep["linkovi"]), len(rep["cdx"]), len(rep["pretraga"]))
                if run.fc_stopped:
                    break
            log.info("discover: HTTP %d, Firecrawl %d poziva", run.fetcher.network_calls,
                     run.fc.calls)
            return 0

        if args.only:
            izvori = filter_izvori(izvori, args.only, liste)

        def fetch(src):
            return run.fetch(src)

        out = P.build_output(liste, izvori, fetch, store=run.store)
        if args.only:
            log.info("--only %s: %d dokumenata (programi.json se ne piše)", args.only,
                     len(out["dokumenti"]))
            for d in out["dokumenti"]:
                log.info("  %s %-12s %-8s %4s str. %6s riječi  %s", d["doc_id"], d["vrsta"],
                         d["format"], d["stranica"], d["rijeci"], d["naslov"])
            return 0

        old = load_json(args.out) if args.out.exists() else None
        out = P.stable(out, old)
        errs = P.validate(out, liste)
        if errs:
            for e in errs:
                log.error("validacija: %s", e)
            return 1
        args.out.write_text(P.dump(out), encoding="utf-8")
        summarise(out)
        log.info("HTTP mrežnih poziva %d, Firecrawl %d; zapisano %s", run.fetcher.network_calls,
                 run.fc.calls, args.out)
        if run.fc_stopped:
            log.error("Firecrawl zaustavljen: %s", run.fc_stopped)
        return 0
    finally:
        run.fetcher.close()


def filter_izvori(izvori: dict, only: str, liste: dict) -> dict:
    """Keep the sources touching one party (its own + its coalitions)."""
    pid_lists = {s["slug"]: s["list_ids"] for s in liste["stranke"]}
    keep_lists = set(pid_lists.get(only, [])) | {only}
    return {
        "stranke": {k: v for k, v in izvori.get("stranke", {}).items() if k == only},
        "koalicije": {k: v for k, v in izvori.get("koalicije", {}).items() if k in keep_lists},
        "manjine": {k: v for k, v in izvori.get("manjine", {}).items() if k in keep_lists},
    }


def summarise(out: dict) -> None:
    docs = {d["doc_id"]: d for d in out["dokumenti"]}
    for s in out["stranke"]:
        kinds = ",".join(sorted({docs[d]["vrsta"] for d in s["doc_ids"]})) or "-"
        log.info("  %-62s %-13s %s", s["slug"], s["status"], kinds)
    by = {k: sum(1 for s in out["stranke"] if s["status"] == k) for k in P.STATUSI}
    log.info("stranke: %s; dokumenata %d (skenirano %d, stranica %d)", by, len(docs),
             sum(1 for d in docs.values() if d["format"] == "skeniran"),
             sum(d["stranica"] or 0 for d in docs.values()))


if __name__ == "__main__":
    sys.exit(main())
