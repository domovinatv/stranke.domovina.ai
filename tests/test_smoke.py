"""Offline smoke tests: the normalizers every pipeline step relies on."""

from src.normalize import norm_key, slugify, strip_diacritics


def test_strip_diacritics_maps_all_croatian_letters():
    # Đ/đ do not decompose under NFKD, so they need the explicit map.
    assert strip_diacritics("ČčĆćĐđŠšŽž") == "CcCcDdSsZz"


def test_norm_key_ignores_case_diacritics_and_punctuation():
    registar = "HRVATSKA DEMOKRATSKA ZAJEDNICA - HDZ"
    nsk = "Hrvatska demokratska zajednica (HDZ)"
    assert norm_key(registar) == norm_key(nsk) == "hrvatska demokratska zajednica hdz"
    assert norm_key("Đurđevac, Šibenik i Čakovec!") == "durdevac sibenik i cakovec"


def test_slugify_croatian_name():
    assert slugify("  Hrvatska seljačka stranka – HSS ") == "hrvatska-seljacka-stranka-hss"
