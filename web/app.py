"""FastAPI + HTMX katalog hrvatskih političkih stranaka.

Run with:
    uv run uvicorn web.app:app --reload --port 8000

Reads the same SQLite DB the ingest scripts populate. HTMX-driven so the list /
filter sidebar / search box update without full page reloads, but every URL
remains a real GET so deep-linking works and crawlers see content.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import csv
import io

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.db import connect  # noqa: E402
from src.normalize import strip_diacritics  # noqa: E402

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent

TEMPLATES = Jinja2Templates(directory=str(ROOT / "templates"))

app = FastAPI(title="DOMOVINA Stranke — Hrvatske političke stranke", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

PAGE_SIZE = 30

STATUS_CHOICES = ("aktivne", "ugasene", "sve")

CONTACT_FIELDS = (
    "address", "email", "phone", "website",
    "fb_url", "ig_url", "x_url", "president",
)

# Neutral initial-letter avatar palette (no party logos yet). Deterministic
# per-name so the same party always gets the same colour.
_AVATAR_COLORS = (
    "bg-rose-100 text-rose-700",
    "bg-orange-100 text-orange-700",
    "bg-amber-100 text-amber-700",
    "bg-lime-100 text-lime-700",
    "bg-emerald-100 text-emerald-700",
    "bg-teal-100 text-teal-700",
    "bg-sky-100 text-sky-700",
    "bg-indigo-100 text-indigo-700",
    "bg-violet-100 text-violet-700",
    "bg-fuchsia-100 text-fuchsia-700",
)


def _avatar(name: str) -> tuple[str, str]:
    """(initial, tailwind colour classes) for the neutral avatar circle."""
    initial = next((ch for ch in name if ch.isalnum()), "?").upper()
    color = _AVATAR_COLORS[sum(ord(ch) for ch in name) % len(_AVATAR_COLORS)]
    return initial, color


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _conn() -> sqlite3.Connection:
    return connect()


def _global_stats(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN status = 'AKTIVAN' THEN 1 ELSE 0 END) AS active,
          SUM(CASE WHEN status = 'PRESTANAK' THEN 1 ELSE 0 END) AS defunct,
          SUM(CASE WHEN city IS NOT NULL THEN 1 ELSE 0 END) AS with_city,
          SUM(CASE WHEN lat IS NOT NULL AND lng IS NOT NULL THEN 1 ELSE 0 END) AS with_coords,
          SUM(CASE WHEN phone_kind = 'mobile' THEN 1 ELSE 0 END) AS can_sms,
          SUM(CASE WHEN phone IS NOT NULL THEN 1 ELSE 0 END) AS can_call,
          SUM(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) AS can_email,
          SUM(CASE WHEN address IS NOT NULL THEN 1 ELSE 0 END) AS can_mail,
          SUM(CASE WHEN website IS NOT NULL THEN 1 ELSE 0 END) AS with_website,
          SUM(CASE WHEN
            fb_url IS NOT NULL OR ig_url IS NOT NULL OR x_url IS NOT NULL
            THEN 1 ELSE 0 END) AS with_social,
          SUM(CASE WHEN
            website IS NOT NULL OR fb_url IS NOT NULL OR ig_url IS NOT NULL
            OR x_url IS NOT NULL
            THEN 1 ELSE 0 END) AS can_web,
          SUM(CASE WHEN
            phone_kind = 'mobile' AND phone IS NOT NULL
            AND email IS NOT NULL AND address IS NOT NULL
            AND (website IS NOT NULL OR fb_url IS NOT NULL OR ig_url IS NOT NULL
                 OR x_url IS NOT NULL)
            THEN 1 ELSE 0 END) AS full_contact,
          SUM(CASE WHEN
            phone IS NULL AND email IS NULL AND address IS NULL
            AND website IS NULL AND fb_url IS NULL AND ig_url IS NULL
            AND x_url IS NULL
            THEN 1 ELSE 0 END) AS unreachable
        FROM parties
        """
    ).fetchone()
    return dict(row)


def _cities(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT city AS name, COUNT(*) AS n
        FROM parties
        WHERE city IS NOT NULL
        GROUP BY city
        ORDER BY n DESC, city
        """
    ).fetchall()
    return [dict(r) for r in rows]


_ACTION_SCORE_SQL = (
    "((CASE WHEN p.phone_kind = 'mobile' THEN 1 ELSE 0 END) + "
    " (CASE WHEN p.phone IS NOT NULL THEN 1 ELSE 0 END) + "
    " (CASE WHEN p.email IS NOT NULL THEN 1 ELSE 0 END) + "
    " (CASE WHEN p.address IS NOT NULL THEN 1 ELSE 0 END) + "
    " (CASE WHEN p.website IS NOT NULL OR p.fb_url IS NOT NULL "
    "       OR p.ig_url IS NOT NULL OR p.x_url IS NOT NULL THEN 1 ELSE 0 END))"
)


def _enrich_parties(rows: list[dict]) -> list[dict]:
    """Decorate plain party rows with avatar + reachability flags."""
    for r in rows:
        r["initial"], r["avatar_color"] = _avatar(r["canonical_name"])
        r["reg_year"] = (r.get("registered_at") or "")[:4] or None
        r["can_sms"] = r.get("phone_kind") == "mobile"
        r["can_call"] = bool(r.get("phone"))
        r["can_email"] = bool(r.get("email"))
        r["can_mail"] = bool(r.get("address"))
        r["can_web"] = bool(
            r.get("website") or r.get("fb_url") or r.get("ig_url") or r.get("x_url")
        )
        r["action_score"] = sum([
            r["can_sms"], r["can_call"], r["can_email"],
            r["can_mail"], r["can_web"],
        ])
        r["is_full"] = r["action_score"] == 5
    return rows


def _city_stats(conn, name: str) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN status = 'AKTIVAN' THEN 1 ELSE 0 END) AS active,
          SUM(CASE WHEN status = 'PRESTANAK' THEN 1 ELSE 0 END) AS defunct,
          SUM(CASE WHEN phone_kind = 'mobile' THEN 1 ELSE 0 END) AS can_sms,
          SUM(CASE WHEN phone IS NOT NULL THEN 1 ELSE 0 END) AS can_call,
          SUM(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) AS can_email,
          SUM(CASE WHEN address IS NOT NULL THEN 1 ELSE 0 END) AS can_mail,
          SUM(CASE WHEN
            website IS NOT NULL OR fb_url IS NOT NULL OR ig_url IS NOT NULL
            OR x_url IS NOT NULL
            THEN 1 ELSE 0 END) AS can_web,
          SUM(CASE WHEN
            phone_kind = 'mobile' AND phone IS NOT NULL
            AND email IS NOT NULL AND address IS NOT NULL
            AND (website IS NOT NULL OR fb_url IS NOT NULL OR ig_url IS NOT NULL
                 OR x_url IS NOT NULL)
            THEN 1 ELSE 0 END) AS full_contact,
          SUM(CASE WHEN
            phone IS NULL AND email IS NULL AND address IS NULL
            AND website IS NULL AND fb_url IS NULL AND ig_url IS NULL
            AND x_url IS NULL
            THEN 1 ELSE 0 END) AS unreachable
        FROM parties WHERE city = ?
        """,
        (name,),
    ).fetchone()
    return dict(row)


def _filtered_parties(
    conn: sqlite3.Connection,
    *,
    q: str | None,
    grad: str | None,
    status: str,
    has_email: bool,
    has_phone: bool,
    has_web: bool,
    has_social: bool,
    only_full: bool = False,
    page: int | None = 1,
    per_page: int = PAGE_SIZE,
) -> tuple[list[dict], int]:
    where: list[str] = []
    params: list = []
    if status == "aktivne":
        where.append("p.status = 'AKTIVAN'")
    elif status == "ugasene":
        where.append("p.status = 'PRESTANAK'")
    if grad:
        where.append("p.city = ?")
        params.append(grad)
    if q:
        # Route search through parties_fts (FTS5). Each word becomes a prefix
        # match so "domov" hits "domovinski". Normalize the query the same way
        # we normalized the index so "đakovo" / "Dakovo" / "dakovo" collide.
        tokens = [w for w in strip_diacritics(q).lower().split() if w]
        if tokens:
            fts_query = " ".join(f'"{w}"*' for w in tokens)
            where.append(
                "p.slug IN (SELECT slug FROM parties_fts WHERE parties_fts MATCH ?)"
            )
            params.append(fts_query)
        else:
            where.append("1 = 0")  # empty query post-norm → no results
    if has_email:
        where.append("p.email IS NOT NULL")
    if has_phone:
        where.append("p.phone IS NOT NULL")
    if has_web:
        where.append("p.website IS NOT NULL")
    if has_social:
        where.append(
            "(p.fb_url IS NOT NULL OR p.ig_url IS NOT NULL OR p.x_url IS NOT NULL)"
        )
    if only_full:
        where.append(f"{_ACTION_SCORE_SQL} = 5")
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    count_sql = f"SELECT COUNT(*) AS n FROM parties p {where_sql}"
    total = conn.execute(count_sql, params).fetchone()["n"]

    # page=None means "all rows" (used by /export.csv).
    if page is None:
        limit_sql = ""
    else:
        offset = max(0, (page - 1) * per_page)
        limit_sql = f" LIMIT {per_page} OFFSET {offset}"
    list_sql = (
        f"SELECT p.* FROM parties p {where_sql} "
        " ORDER BY p.canonical_name "
        f" {limit_sql}"
    )
    rows = _enrich_parties([dict(r) for r in conn.execute(list_sql, params).fetchall()])
    return rows, total


def _people(conn, party_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT full_name, role, represents, source
        FROM party_people
        WHERE party_id = ?
        ORDER BY CASE WHEN role = 'PREDSJEDNIK' THEN 0 ELSE 1 END, role, full_name
        """,
        (party_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _functions_grouped(conn, party_id: int) -> list[dict]:
    """Povijesne funkcije grouped by function name, mandates newest-first."""
    rows = conn.execute(
        """
        SELECT function, holder, mandate_start, mandate_end, source
        FROM party_functions
        WHERE party_id = ?
        ORDER BY function, mandate_start DESC, holder
        """,
        (party_id,),
    ).fetchall()
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["function"], []).append(dict(r))
    return [{"function": fn, "entries": entries} for fn, entries in grouped.items()]


def _aliases(conn, party_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT alias, source FROM party_aliases WHERE party_id = ? "
        "AND source NOT LIKE '%-id'",  # exclude opaque numeric IDs
        (party_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------- Routes ----------

def _truthy(v: str | None) -> bool:
    # Form/links serialize unchecked boxes as empty string; FastAPI's bool
    # type rejects "" with 422, so accept strings and convert ourselves.
    return v not in (None, "", "0", "false", "False")


def _norm_status(v: str | None) -> str:
    return v if v in STATUS_CHOICES else "aktivne"


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    q: str | None = Query(None),
    grad: str | None = Query(None),
    status: str | None = Query(None),
    has_email: str | None = Query(None),
    has_phone: str | None = Query(None),
    has_web: str | None = Query(None),
    has_social: str | None = Query(None),
    only_full: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    status_v = _norm_status(status)
    has_email_b = _truthy(has_email)
    has_phone_b = _truthy(has_phone)
    has_web_b = _truthy(has_web)
    has_social_b = _truthy(has_social)
    only_full_b = _truthy(only_full)
    with _conn() as conn:
        parties, total = _filtered_parties(
            conn, q=q, grad=grad, status=status_v,
            has_email=has_email_b, has_phone=has_phone_b,
            has_web=has_web_b, has_social=has_social_b,
            only_full=only_full_b, page=page,
        )
        ctx = {
            "request": request,
            "parties": parties,
            "total": total,
            "page": page,
            "page_size": PAGE_SIZE,
            "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
            "q": q or "",
            "grad": grad or "",
            "status": status_v,
            "has_email": has_email_b,
            "has_phone": has_phone_b,
            "has_web": has_web_b,
            "has_social": has_social_b,
            "only_full": only_full_b,
            "cities": _cities(conn),
            "stats": _global_stats(conn),
        }
    # HTMX requests want just the partial that re-renders the list region.
    if _is_htmx(request):
        return TEMPLATES.TemplateResponse(request, "partials/party_list.html", ctx)
    return TEMPLATES.TemplateResponse(request, "index.html", ctx)


@app.get("/stranke/{slug}", response_class=HTMLResponse)
def party_detail(slug: str, request: Request):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM parties WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return HTMLResponse("Not found", status_code=404)
        party = _enrich_parties([dict(row)])[0]
        party["people"] = _people(conn, party["id"])
        party["functions"] = _functions_grouped(conn, party["id"])
        party["aliases"] = _aliases(conn, party["id"])
        runs = conn.execute(
            "SELECT ran_at, fields_filled, source_urls FROM backfill_runs "
            "WHERE party_id = ? ORDER BY ran_at DESC LIMIT 5",
            (party["id"],),
        ).fetchall()
        party["backfill_runs"] = [dict(r) for r in runs]
    return TEMPLATES.TemplateResponse(
        request, "party.html", {"party": party, "contact_fields": CONTACT_FIELDS},
    )


@app.get("/export.csv")
def export_csv(
    q: str | None = Query(None),
    grad: str | None = Query(None),
    status: str | None = Query(None),
    has_email: str | None = Query(None),
    has_phone: str | None = Query(None),
    has_web: str | None = Query(None),
    has_social: str | None = Query(None),
    only_full: str | None = Query(None),
):
    """Stream the currently-filtered set as a CSV with contact-friendly columns."""
    status_v = _norm_status(status)
    with _conn() as conn:
        parties, _ = _filtered_parties(
            conn, q=q, grad=grad, status=status_v,
            has_email=_truthy(has_email),
            has_phone=_truthy(has_phone),
            has_web=_truthy(has_web),
            has_social=_truthy(has_social),
            only_full=_truthy(only_full),
            page=None,  # all rows
        )

    columns = [
        "slug", "canonical_name", "short_name", "oib", "reg_number",
        "status", "registered_at", "status_date", "city", "address",
        "county", "phone", "phone_kind", "phone_e164", "email", "website",
        "fb_url", "ig_url", "x_url", "president", "wiki_url",
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for p in parties:
        w.writerow([p.get(col) or "" for col in columns])
    body = buf.getvalue()
    filename_parts = ["stranke"]
    if grad:
        filename_parts.append(grad.split()[0].lower())
    if status_v != "sve":
        filename_parts.append(status_v)
    if _truthy(only_full):
        filename_parts.append("punkontakt")
    fname = "-".join(filename_parts) + ".csv"
    return StreamingResponse(
        iter([body]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/gradovi/{name}", response_class=HTMLResponse)
def city_detail(name: str, request: Request):
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM parties WHERE city = ?", (name,)
        ).fetchone()
        if not row["n"]:
            return HTMLResponse("Nepoznat grad", status_code=404)

        rows = conn.execute(
            "SELECT * FROM parties WHERE city = ? ORDER BY canonical_name",
            (name,),
        ).fetchall()
        parties = _enrich_parties([dict(r) for r in rows])
        stats = _city_stats(conn, name)

    return TEMPLATES.TemplateResponse(
        request, "city.html",
        {
            "city_name": name,
            "parties": parties,
            "stats": stats,
        },
    )


@app.get("/map", response_class=HTMLResponse)
def map_view(request: Request):
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.slug, p.canonical_name, p.short_name, p.city,
                   p.status, p.lat, p.lng, p.phone, p.email
            FROM parties p
            WHERE p.lat IS NOT NULL AND p.lng IS NOT NULL
            """
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM parties").fetchone()[0]
    parties = [dict(r) for r in rows]
    import json as _json
    return TEMPLATES.TemplateResponse(
        request, "map.html",
        {
            "parties_json": _json.dumps(parties, ensure_ascii=False),
            "geo_count": len(parties),
            "total": total,
        },
    )


@app.get("/api/stats")
def api_stats() -> JSONResponse:
    with _conn() as conn:
        return JSONResponse({
            "global": _global_stats(conn),
            "cities": _cities(conn),
        })
