from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Croatian Đ/đ don't decompose under NFKD (they're standalone letters, not
# base+combining), so we map them explicitly before the general pass.
_CROATIAN_MAP = str.maketrans({"đ": "d", "Đ": "D"})


def strip_diacritics(s: str) -> str:
    s = s.translate(_CROATIAN_MAP)
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def slugify(name: str) -> str:
    base = strip_diacritics(name).lower().strip()
    base = _NON_ALNUM.sub("-", base).strip("-")
    return base


def norm_key(name: str) -> str:
    """Case/diacritics/punctuation-insensitive key for cross-source matching
    (registar NAZIV vs NSK NazivStranke)."""
    return _NON_ALNUM.sub(" ", strip_diacritics(name).lower()).strip()
