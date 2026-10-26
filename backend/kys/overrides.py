"""Kullanıcının elle düzelttiği doküman kimlikleri (kod, revizyon, başlık, tip).

Veritabanı yeniden kurulsa da kaybolmasın diye dosya içeriğinin SHA-256'sı ile anahtarlanıp
JSON dosyasında tutulur (varsayılan: data/kys_overrides.json). Yükleme ve sınıflandırma her zaman
bu değerleri en son uygular; kullanıcı kararı modelin ve kuralların önündedir.
"""

import json
from pathlib import Path

from . import config

FIELDS = ("code", "revision", "title", "doc_type")


def _path() -> Path:
    return config.settings.overrides_path


def load() -> dict[str, dict]:
    p = _path()
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def get(sha256: str) -> dict | None:
    return load().get(sha256)


def put(sha256: str, file_name: str, **fields) -> None:
    data = load()
    entry = data.get(sha256, {"dosya": file_name})
    entry.update({k: v for k, v in fields.items() if k in FIELDS and v})
    data[sha256] = entry
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
