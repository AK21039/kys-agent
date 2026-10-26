from kys.textnorm import fold, verify_quote


def test_fold_turkish_letters_to_ascii_lowercase():
    assert fold("Satınalma İŞLEMLERİ  ve   Çağrı ÖĞÜ") == "satinalma islemleri ve cagri ogu"


def test_fold_matches_text_typed_without_turkish_chars():
    assert fold("Görev Tanımı") == fold("gorev tanimi")


def test_verify_quote_accepts_formatting_differences():
    source = "| 4.2 | Satınalma talebi 100.000 TL’yi aşarsa  **Genel Müdür** onaylar. |"
    assert verify_quote("Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar", source)


def test_verify_quote_rejects_fabricated_quote():
    source = "Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar."
    assert not verify_quote("Satınalma talebi 50.000 TL'yi aşarsa Genel Müdür onaylar.", source)


def test_verify_quote_rejects_too_short_quote():
    assert not verify_quote("onaylar", "Genel Müdür onaylar.")
