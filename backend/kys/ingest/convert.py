"""Eski Office biçimlerini (.doc/.xls) Windows'ta Word/Excel COM ile .docx/.xlsx'e çevirir.

Orijinal dosyalara dokunulmaz; çıktı ayrı klasöre yazılır. COM, PowerShell alt süreciyle çağrılır
(`powershell -NoProfile -Command`; cmd kullanılmaz). Yol ve klasörler ortam değişkeniyle geçilir, böylece
Türkçe karakter / boşluk / tırnak sorunu olmaz.
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CONVERTIBLE = {".doc": ".docx", ".xls": ".xlsx"}
_WD_FORMAT_DOCX = 16  # wdFormatXMLDocument
_XL_FORMAT_XLSX = 51  # xlOpenXMLWorkbook


class ConvertError(Exception):
    pass


@dataclass
class ConvertResult:
    src: Path
    dst: Path | None
    status: str  # 'donusturuldu' | 'atlandi' | 'hata'
    message: str = ""


_PS_WORD = r"""
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject Word.Application
$app.Visible = $false
$app.DisplayAlerts = 0
try {
  $doc = $app.Documents.Open($env:KYS_SRC, $false, $true)
  try { $doc.SaveAs2($env:KYS_DST, %d) } finally { $doc.Close($false) }
} finally { $app.Quit() }
"""
_PS_EXCEL = r"""
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject Excel.Application
$app.Visible = $false
$app.DisplayAlerts = $false
try {
  $wb = $app.Workbooks.Open($env:KYS_SRC, 0, $true)
  try { $wb.SaveAs($env:KYS_DST, %d) } finally { $wb.Close($false) }
} finally { $app.Quit() }
"""


def com_available() -> bool:
    return sys.platform == "win32" and shutil.which("powershell") is not None


def convert_file(src: Path, dst: Path, timeout: int = 180) -> None:
    """Tek dosyayı çevirir; hata durumunda ConvertError."""
    if not com_available():
        raise ConvertError("Word/Excel COM yalnızca Windows'ta ve PowerShell ile kullanılabilir; "
                           "alternatif: LibreOffice (soffice --headless --convert-to docx).")
    ext = src.suffix.lower()
    if ext == ".doc":
        script = _PS_WORD % _WD_FORMAT_DOCX
    elif ext == ".xls":
        script = _PS_EXCEL % _XL_FORMAT_XLSX
    else:
        raise ConvertError(f"Dönüştürülemeyen uzantı: {ext}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, KYS_SRC=str(src.resolve()), KYS_DST=str(dst.resolve()))
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                           env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ConvertError(f"Zaman aşımı ({timeout} sn): {src.name}")
    if p.returncode != 0 or not dst.exists():
        err = (p.stderr or p.stdout or "").strip().splitlines()
        raise ConvertError(err[0] if err else f"Dönüştürme başarısız (çıkış kodu {p.returncode}).")


def convert_folder(folder: Path, out: Path, overwrite: bool = False, progress=None) -> list[ConvertResult]:
    """Klasördeki (alt klasörler dahil) .doc/.xls dosyalarını `out` altına, göreli yapıyı koruyarak çevirir.
    ~$ ile başlayan geçici dosyalar yok sayılır."""
    folder, out = Path(folder), Path(out)
    results: list[ConvertResult] = []
    files = sorted(p for p in folder.rglob("*")
                   if p.is_file() and p.suffix.lower() in CONVERTIBLE and not p.name.startswith("~$"))
    for src in files:
        dst = out / src.relative_to(folder).with_suffix(CONVERTIBLE[src.suffix.lower()])
        if dst.exists() and not overwrite:
            r = ConvertResult(src, dst, "atlandi", "çıktı zaten var")
        else:
            try:
                convert_file(src, dst)
                r = ConvertResult(src, dst, "donusturuldu")
            except ConvertError as e:
                r = ConvertResult(src, None, "hata", str(e))
        results.append(r)
        if progress:
            progress(r)
    return results
