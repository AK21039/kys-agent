"""Ayarlar. Model adları ve yollar yalnızca burada (ve .env'de) tanımlıdır."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# SQLite ağ paylaşımında (W:) güvenilir kilitlenmez; veritabanı varsayılan olarak yerel diskte durur.
LOCAL_HOME = Path(os.getenv("LOCALAPPDATA", Path.home())) / "kys-agent"

# openai: OpenAI uyumlu herhangi bir uç nokta (GLM, Gemini, Workers AI, OpenRouter, Groq, LM Studio...)
# gemini: Google'ın OpenAI uyumlu uç noktası (anahtar GEMINI_API_KEY)
PROVIDERS = ("anthropic", "ollama", "openai", "gemini")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
# Sorgu katmanı model zinciri varsayılanı: sırayla denenir (kota/geçici hata → sıradaki)
DEFAULT_QUERY_CHAIN = "gemini:gemini-3.6-flash,gemini:gemini-3.1-flash-lite,anthropic:claude-haiku-5-5"
# BYOK'ta kullanıcı yalnızca bu sağlayıcılardan birini seçebilir
BYOK_PROVIDERS = ("gemini", "anthropic")


@dataclass(frozen=True)
class ModelSpec:
    provider: str   # 'anthropic' | 'ollama' | 'openai' | 'gemini'
    model: str

    @classmethod
    def parse(cls, value: str) -> "ModelSpec":
        """'ollama:gemma4:latest' → (ollama, gemma4:latest). Öneksiz değer Anthropic modelidir."""
        provider, sep, model = value.partition(":")
        if sep and provider in PROVIDERS:
            return cls(provider, model)
        return cls("anthropic", value)

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def parse_chain(value: str) -> tuple[ModelSpec, ...]:
    """'a:x,b:y' → (ModelSpec, ModelSpec). Tek değer tek elemanlı zincirdir."""
    return tuple(ModelSpec.parse(v.strip()) for v in value.split(",") if v.strip())


@dataclass(frozen=True)
class Settings:
    model_fast: ModelSpec
    model_smart: ModelSpec
    model_query: tuple[ModelSpec, ...]  # sorgu servisi (asistan cevapları): sırayla denenen model zinciri
    db_path: Path
    overrides_path: Path
    ollama_url: str
    ollama_num_ctx: int
    ollama_timeout: int
    openai_base_url: str
    openai_api_key: str
    # Sorgu servisi
    base_path: str                  # ör. "/qa" → paktenops.com/qa
    access_token: str               # boşsa kimlik doğrulama yok (yalnızca yerel kullanım)
    db_url: str                     # konteyner açılışında DB yoksa buradan indirilir
    allowed_hosts: tuple[str, ...]  # MCP için Host başlığı beyaz listesi (boşsa kontrol yok)
    gemini_api_key: str = ""        # GEMINI_API_KEY
    remote_timeout: int = 90        # openai/gemini istek zaman aşımı (sn); zincirde takılmayı önler
    cors_origins: tuple[str, ...] = ()  # KYS_CORS_ORIGINS; boşsa CORS kapalı
    inbox_dir: Path = Path("data/inbox")  # zamanlanmış yüklemenin okuduğu doküman klasörü (KYS_INBOX_DIR)
    pages_dir: Path | None = None   # önceden üretilmiş PDF sayfa PNG'leri: <pages_dir>/<dosya_sha256>/<n>.png
    publish_bucket: str = ""        # doluysa `kys scheduled` sonunda yayın kopyası buraya (gs://...) yüklenir
    run_service: str = "kys-qa"     # yüklemeden sonra yeni revizyonu başlatılacak Cloud Run servisi
    run_region: str = "europe-west1"
    files_dir: Path | None = None   # orijinal dosyaların bulunabileceği ek klasör (dosya adıyla aranır)


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


settings = Settings(
    model_fast=ModelSpec.parse(os.getenv("KYS_MODEL_FAST", "ollama:gemma4:latest")),
    model_smart=ModelSpec.parse(os.getenv("KYS_MODEL_SMART", "anthropic:claude-sonnet-5-5")),
    model_query=parse_chain(os.getenv("KYS_MODEL_QUERY") or DEFAULT_QUERY_CHAIN),
    db_path=_resolve(os.getenv("KYS_DB_PATH", str(LOCAL_HOME / "kys.db"))),
    # Elle düzeltmeler dokümanların yanında (ağ paylaşımında, yedekli) durur; DB yeniden kurulsa da korunur.
    overrides_path=_resolve(os.getenv("KYS_OVERRIDES_PATH", "data/kys_overrides.json")),
    ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
    ollama_num_ctx=int(os.getenv("KYS_OLLAMA_NUM_CTX", "16384")),
    ollama_timeout=int(os.getenv("KYS_OLLAMA_TIMEOUT", "900")),
    openai_base_url=os.getenv("KYS_OPENAI_BASE_URL", "").rstrip("/"),
    openai_api_key=os.getenv("KYS_OPENAI_API_KEY", "").strip(),  # secret/dosyadan gelen satır sonu başlığı bozar
    gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
    remote_timeout=int(os.getenv("KYS_REMOTE_TIMEOUT", "90")),
    cors_origins=tuple(o.strip().rstrip("/") for o in os.getenv("KYS_CORS_ORIGINS", "").split(",") if o.strip()),
    base_path="/" + os.getenv("KYS_BASE_PATH", "/qa").strip("/"),
    access_token=os.getenv("KYS_ACCESS_TOKEN", ""),
    db_url=os.getenv("KYS_DB_URL", ""),
    allowed_hosts=tuple(h.strip() for h in os.getenv("KYS_ALLOWED_HOSTS", "").split(",") if h.strip()),
    inbox_dir=_resolve(os.getenv("KYS_INBOX_DIR", "data/inbox")),
    pages_dir=_resolve(os.environ["KYS_PAGES_DIR"]) if os.getenv("KYS_PAGES_DIR") else None,
    publish_bucket=os.getenv("KYS_PUBLISH_BUCKET", "").strip(),
    run_service=os.getenv("KYS_RUN_SERVICE", "kys-qa"),
    run_region=os.getenv("KYS_RUN_REGION", "europe-west1"),
    files_dir=_resolve(os.environ["KYS_FILES_DIR"]) if os.getenv("KYS_FILES_DIR") else None,
)
