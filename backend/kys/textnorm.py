"""Türkçe metin normalizasyonu ve alıntı doğrulama."""

import re
import unicodedata

_TR_FOLD = str.maketrans({
    "İ": "i", "I": "i", "ı": "i",
    "Ş": "s", "ş": "s",
    "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u",
    "Ö": "o", "ö": "o",
    "Ç": "c", "ç": "c",
    "Â": "a", "â": "a", "Î": "i", "î": "i", "Û": "u", "û": "u",
})
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})
_WS = re.compile(r"\s+")


def fold_chars(text: str) -> str:
    """Yalnızca karakter katlama (boşluk daraltma ve NFC yok); uzunluk genellikle korunur."""
    return text.translate(_QUOTES).translate(_TR_FOLD).lower()


def fold(text: str) -> str:
    """Aramada kullanılacak katlanmış biçim: Türkçe harfler ASCII'ye, küçük harf, tek boşluk.

    "Satınalma İŞLEMLERİ" -> "satinalma islemleri". Kullanıcı Türkçe karaktersiz yazsa da eşleşir.
    """
    text = unicodedata.normalize("NFC", text).translate(_QUOTES).translate(_TR_FOLD).lower()
    return _WS.sub(" ", text).strip()


def _quote_key(text: str) -> str:
    """Alıntı karşılaştırması için: katla, noktalama ve tablo ayıracı farklarını yok say."""
    return _WS.sub(" ", re.sub(r"[|*_#`\"'.,;:()\[\]-]", " ", fold(text))).strip()


def verify_quote(quote: str, source: str, min_len: int = 12) -> bool:
    """Alıntı kaynak metinde (biçim farkları dışında) birebir geçiyor mu?

    LLM çıktısındaki her kanıt alıntısı bununla doğrulanır (CLAUDE.md değişmez 1).
    Çok kısa alıntılar kanıt sayılmaz.
    """
    q = _quote_key(quote)
    if len(q) < min_len:
        return False
    return q in _quote_key(source)
