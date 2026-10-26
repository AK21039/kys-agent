"""Tüm LLM çağrılarının geçtiği tek kapı (CLAUDE.md değişmez 6).

Sağlayıcı katman bazında seçilir (config: KYS_MODEL_FAST / KYS_MODEL_SMART / KYS_MODEL_QUERY):
- anthropic: Claude, Anthropic SDK ile (yapılandırılmış çıktı + prompt önbelleği)
- ollama: yerel model, Ollama /api/chat ile (JSON şema kısıtlı çıktı); ücretsiz, veri makineden çıkmaz
- openai: OpenAI uyumlu herhangi bir uç nokta (KYS_OPENAI_BASE_URL); GLM, Gemini, Workers AI, OpenRouter...
Durma nedeni kontrolü ve `llm_calls` loglaması her iki sağlayıcı için burada yapılır.
"""

import copy
import json
import sqlite3
import urllib.error
import urllib.request
from functools import lru_cache
from types import SimpleNamespace
from typing import Literal, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from .config import ModelSpec, settings

T = TypeVar("T", bound=BaseModel)
Tier = Literal["fast", "smart", "query"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class LLMError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def client() -> anthropic.Anthropic:
    # Kimlik bilgisi ortamdan çözülür: ANTHROPIC_API_KEY veya `ant auth login` profili.
    return anthropic.Anthropic()


def model_for(tier: Tier) -> ModelSpec:
    return {"fast": settings.model_fast, "smart": settings.model_smart, "query": settings.model_query}[tier]


def _log(conn: sqlite3.Connection | None, *, purpose: str, model: str, usage=None,
         stop_reason: str | None = None, ok: bool, error: str | None = None, ref: str | None = None) -> None:
    if conn is None:
        return
    conn.execute(
        """INSERT INTO llm_calls(purpose, model, input_tokens, output_tokens, cache_read_tokens,
                                 cache_write_tokens, stop_reason, ok, error, ref)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (purpose, model,
         getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None),
         getattr(usage, "cache_read_input_tokens", None), getattr(usage, "cache_creation_input_tokens", None),
         stop_reason, int(ok), error, ref),
    )
    conn.commit()


def structured(
    *,
    purpose: str,
    tier: Tier,
    system: str,
    user: str,
    schema: type[T],
    max_tokens: int = 8000,
    effort: Effort | None = None,
    conn: sqlite3.Connection | None = None,
    ref: str | None = None,
) -> T:
    """Şemaya uygun, doğrulanmış bir Pydantic nesnesi döndürür; aksi halde LLMError."""
    spec = model_for(tier)
    call = {"ollama": _ollama, "openai": _openai}.get(spec.provider, _anthropic)
    try:
        out, usage, stop = call(spec.model, system, user, schema, max_tokens, effort)
    except LLMError as e:
        _log(conn, purpose=purpose, model=str(spec), usage=getattr(e, "usage", None),
             stop_reason=getattr(e, "stop", None), ok=False, error=str(e), ref=ref)
        raise LLMError(f"{purpose}: {e}") from e
    _log(conn, purpose=purpose, model=str(spec), usage=usage, stop_reason=stop, ok=True, ref=ref)
    return out


def _fail(msg: str, usage=None, stop: str | None = None) -> LLMError:
    e = LLMError(msg)
    e.usage, e.stop = usage, stop
    return e


# --- Anthropic ------------------------------------------------------------

def _anthropic(model: str, system: str, user: str, schema: type[T], max_tokens: int, effort):
    kwargs = {"output_config": {"effort": effort}} if effort else {}
    try:
        resp = client().messages.parse(
            model=model,
            max_tokens=max_tokens,
            # Sistem promptu sabit tutulur ve önbelleklenir; değişken içerik `user` içinde gider.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            **kwargs,
        )
    except anthropic.APIError as e:
        raise _fail(f"API hatası: {type(e).__name__}: {e}") from e

    if resp.stop_reason in ("refusal", "max_tokens") or resp.parsed_output is None:
        detail = resp.stop_reason
        if resp.stop_reason == "refusal" and resp.stop_details:
            detail = f"refusal ({resp.stop_details.category})"
        raise _fail(f"geçerli çıktı alınamadı ({detail})", resp.usage, resp.stop_reason)
    return resp.parsed_output, resp.usage, resp.stop_reason


# --- Ollama ---------------------------------------------------------------

def _inline_refs(schema: dict) -> dict:
    """Pydantic şemasındaki $ref/$defs'i açar; Ollama'nın şema→gramer dönüştürücüsü için en güvenli biçim."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = copy.deepcopy(defs[node["$ref"].split("/")[-1]])
                rest = {k: v for k, v in node.items() if k != "$ref"}
                return walk({**target, **rest})
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def _ollama(model: str, system: str, user: str, schema: type[T], max_tokens: int, effort):
    body = {
        "model": model,
        "stream": False,
        "think": False,          # yapılandırılmış çıktıda düşünme modu hız kaybından başka bir şey getirmiyor
        "format": _inline_refs(schema.model_json_schema()),
        "options": {"temperature": 0, "num_ctx": settings.ollama_num_ctx, "num_predict": max_tokens},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    req = urllib.request.Request(f"{settings.ollama_url}/api/chat", json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=settings.ollama_timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise _fail(f"Ollama HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise _fail(f"Ollama'ya ulaşılamadı ({settings.ollama_url}): {e}") from e

    usage = SimpleNamespace(input_tokens=data.get("prompt_eval_count"), output_tokens=data.get("eval_count"))
    stop = data.get("done_reason")
    if stop == "length":
        raise _fail("geçerli çıktı alınamadı (max_tokens)", usage, stop)
    try:
        return schema.model_validate_json(data["message"]["content"]), usage, stop
    except (ValidationError, KeyError) as e:
        raise _fail(f"model çıktısı şemaya uymuyor: {e}", usage, stop) from e


# --- OpenAI uyumlu uç noktalar ----------------------------------------------

def _post_json(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=settings.ollama_timeout) as r:
        return json.load(r)


def _openai(model: str, system: str, user: str, schema: type[T], max_tokens: int, effort):
    if not settings.openai_base_url:
        raise _fail("KYS_OPENAI_BASE_URL tanımlı değil")
    url = f"{settings.openai_base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"} if settings.openai_api_key else {}
    json_schema = _inline_refs(schema.model_json_schema())
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": schema.__name__, "schema": json_schema}},
    }
    try:
        try:
            data = _post_json(url, body, headers)
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            # json_schema desteklemeyen sağlayıcılar: JSON kipine düş, şemayı prompta yaz.
            body["response_format"] = {"type": "json_object"}
            body["messages"][0]["content"] = (
                f"{system}\n\nYalnızca şu JSON şemasına uyan tek bir JSON nesnesi döndür:\n"
                f"{json.dumps(json_schema, ensure_ascii=False)}")
            data = _post_json(url, body, headers)
    except urllib.error.HTTPError as e:
        raise _fail(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise _fail(f"uç noktaya ulaşılamadı ({settings.openai_base_url}): {e}") from e

    u = data.get("usage") or {}
    usage = SimpleNamespace(input_tokens=u.get("prompt_tokens"), output_tokens=u.get("completion_tokens"))
    try:
        choice = data["choices"][0]
        stop = choice.get("finish_reason")
        if stop == "length":
            raise _fail("geçerli çıktı alınamadı (max_tokens)", usage, stop)
        content = choice["message"]["content"] or ""
        content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return schema.model_validate_json(content), usage, stop
    except (ValidationError, KeyError, IndexError) as e:
        raise _fail(f"model çıktısı şemaya uymuyor: {e}", usage) from e
