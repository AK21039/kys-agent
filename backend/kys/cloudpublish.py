"""Yayın kopyasını Cloud Storage'a yükleyip Cloud Run'a yeni veritabanını gösterir.

`gcloud` PowerShell alt süreciyle çağrılır (cmd.exe şirket politikasıyla kapalı; ADC kurulumu gerekmez,
kullanıcının `gcloud auth login` oturumu kullanılır). Sır içermez.
"""

import logging
import shutil
import subprocess
import time
from pathlib import Path

log = logging.getLogger("kys.cloudpublish")


def _q(arg: str) -> str:
    return "'" + str(arg).replace("'", "''") + "'"


def gcloud(*args: str, timeout: int = 1800) -> str:
    """gcloud'u `powershell -NoProfile -Command` ile çalıştırır; hata olursa RuntimeError."""
    shell = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
    cmd = "& gcloud " + " ".join(_q(a) for a in args) + "; exit $LASTEXITCODE"
    r = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", cmd],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"gcloud {' '.join(args[:3])} başarısız (kod {r.returncode}): {(r.stderr or r.stdout).strip()[-500:]}")
    return r.stdout


def upload(db_file: Path, pages_dir: Path | None, bucket: str, *, service: str = "kys-qa",
           region: str = "europe-west1", restart: bool = True) -> None:
    """kys.db ve pages/ klasörünü bucket'a yükler; restart ise Cloud Run'da yeni revizyon başlatır.

    Yeni revizyon gerekçesi: sorgu servisi DB'yi `immutable` açar ve gcsfuse metadata önbelleğini tutar;
    dosya değişince çalışan örnekler eski/karışık içerik görebilir. Ortam değişkeni güncellemesi yeni revizyon
    üretir (trafik otomatik ona geçer, en fazla birkaç saniye kesinti olmaz).
    """
    bucket = bucket.rstrip("/")
    if not bucket.startswith("gs://"):
        bucket = "gs://" + bucket
    log.info("Yükleniyor: %s → %s/kys.db", db_file, bucket)
    gcloud("storage", "cp", str(db_file), f"{bucket}/kys.db")
    if pages_dir and Path(pages_dir).is_dir():
        gcloud("storage", "rsync", str(pages_dir), f"{bucket}/pages", "--recursive")
    if restart:
        gcloud("run", "services", "update", service, "--region", region,
               "--update-env-vars", f"KYS_DB_REV={int(time.time())}", "--quiet")
