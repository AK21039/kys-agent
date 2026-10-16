import dataclasses
import io
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from kys import llm
from kys.config import ModelSpec
from kys.ontology import DocType


class Out(BaseModel):
    value: str


class WithEnum(BaseModel):
    doc_type: DocType
    code: str | None


def _use(monkeypatch, fast: str, smart: str):
    monkeypatch.setattr(llm, "settings", dataclasses.replace(
        llm.settings, model_fast=ModelSpec.parse(fast), model_smart=ModelSpec.parse(smart)))


def test_model_spec_parse():
    assert ModelSpec.parse("ollama:gemma4:latest") == ModelSpec("ollama", "gemma4:latest")
    assert ModelSpec.parse("anthropic:claude-sonnet-5-5") == ModelSpec("anthropic", "claude-sonnet-5-5")
    assert ModelSpec.parse("claude-haiku-5-5") == ModelSpec("anthropic", "claude-haiku-5-5")


# --- Anthropic ------------------------------------------------------------

def _resp(stop_reason="end_turn", parsed=None, stop_details=None):
    usage = SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=0,
                            cache_creation_input_tokens=80)
    return SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed, usage=usage, stop_details=stop_details)


@pytest.fixture
def fake_anthropic(monkeypatch):
    _use(monkeypatch, "anthropic:claude-haiku-5-5", "anthropic:claude-sonnet-5-5")
    calls = {}

    def install(response):
        def parse(**kwargs):
            calls.update(kwargs)
            return response
        monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(messages=SimpleNamespace(parse=parse)))
        return calls
    return install


def test_anthropic_returns_parsed_output_logs_call_and_caches_system(conn, fake_anthropic):
    calls = fake_anthropic(_resp(parsed=Out(value="ok")))
    out = llm.structured(purpose="test", tier="fast", system="S", user="U", schema=Out, conn=conn)
    assert out.value == "ok"
    assert calls["model"] == "claude-haiku-5-5"
    assert calls["system"][0]["cache_control"] == {"type": "ephemeral"}
    row = conn.execute("SELECT * FROM llm_calls").fetchone()
    assert (row["purpose"], row["model"], row["ok"], row["input_tokens"]) == \
           ("test", "anthropic:claude-haiku-5-5", 1, 100)


def test_anthropic_refusal_raises_and_logs_failure(conn, fake_anthropic):
    fake_anthropic(_resp(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber")))
    with pytest.raises(llm.LLMError, match="refusal"):
        llm.structured(purpose="test", tier="smart", system="S", user="U", schema=Out, conn=conn)
    row = conn.execute("SELECT ok, stop_reason, input_tokens FROM llm_calls").fetchone()
    assert (row["ok"], row["stop_reason"], row["input_tokens"]) == (0, "refusal", 100)


def test_anthropic_passes_effort(fake_anthropic):
    calls = fake_anthropic(_resp(parsed=Out(value="ok")))
    llm.structured(purpose="t", tier="smart", system="S", user="U", schema=Out, effort="low")
    assert calls["output_config"] == {"effort": "low"}
    assert calls["model"] == "claude-sonnet-5-5"


# --- Ollama ---------------------------------------------------------------

@pytest.fixture
def fake_ollama(monkeypatch):
    _use(monkeypatch, "ollama:gemma4:latest", "anthropic:claude-sonnet-5-5")
    sent = {}

    def install(content: str, done_reason="stop"):
        def urlopen(req, timeout):
            sent["url"], sent["body"] = req.full_url, json.loads(req.data)
            payload = {"message": {"content": content}, "done_reason": done_reason,
                       "prompt_eval_count": 50, "eval_count": 10}
            return io.BytesIO(json.dumps(payload).encode())
        monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
        return sent
    return install


def test_ollama_sends_inlined_schema_and_parses_output(conn, fake_ollama):
    sent = fake_ollama('{"doc_type": "PROSEDUR", "code": "PR-04"}')
    out = llm.structured(purpose="sinif", tier="fast", system="S", user="Ü", schema=WithEnum, conn=conn)
    assert out.doc_type == DocType.PROSEDUR and out.code == "PR-04"
    body = sent["body"]
    assert sent["url"].endswith("/api/chat") and body["model"] == "gemma4:latest"
    assert "$defs" not in json.dumps(body["format"]) and "$ref" not in json.dumps(body["format"])
    assert "PROSEDUR" in body["format"]["properties"]["doc_type"]["enum"]
    assert body["messages"][1]["content"] == "Ü"
    row = conn.execute("SELECT model, ok, input_tokens, output_tokens FROM llm_calls").fetchone()
    assert tuple(row) == ("ollama:gemma4:latest", 1, 50, 10)


def test_ollama_invalid_output_raises(conn, fake_ollama):
    fake_ollama('{"doc_type": "BILINMEYEN"}')
    with pytest.raises(llm.LLMError, match="şemaya uymuyor"):
        llm.structured(purpose="sinif", tier="fast", system="S", user="U", schema=WithEnum, conn=conn)
    assert conn.execute("SELECT ok FROM llm_calls").fetchone()[0] == 0


def test_ollama_truncated_output_raises(fake_ollama):
    fake_ollama('{"doc_ty', done_reason="length")
    with pytest.raises(llm.LLMError, match="max_tokens"):
        llm.structured(purpose="sinif", tier="fast", system="S", user="U", schema=WithEnum)


def test_ollama_unreachable_raises(monkeypatch):
    _use(monkeypatch, "ollama:gemma4:latest", "anthropic:claude-sonnet-5-5")

    def down(req, timeout):
        raise llm.urllib.error.URLError("connection refused")
    monkeypatch.setattr(llm.urllib.request, "urlopen", down)
    with pytest.raises(llm.LLMError, match="ulaşılamadı"):
        llm.structured(purpose="sinif", tier="fast", system="S", user="U", schema=Out)


# --- OpenAI uyumlu ------------------------------------------------------------

def _use_openai(monkeypatch):
    monkeypatch.setattr(llm, "settings", dataclasses.replace(
        llm.settings, model_query=(ModelSpec.parse("openai:glm-4.5-flash"),),
        openai_base_url="https://ornek.ai/v1", openai_api_key="k"))


def _openai_reply(content, finish="stop"):
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}, "finish_reason": finish}],
                                  "usage": {"prompt_tokens": 30, "completion_tokens": 5}}).encode())


def test_openai_compatible_uses_json_schema(conn, monkeypatch):
    _use_openai(monkeypatch)
    sent = {}

    def urlopen(req, timeout):
        sent["url"], sent["body"], sent["auth"] = req.full_url, json.loads(req.data), req.get_header("Authorization")
        return _openai_reply('{"value": "ok"}')
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    out = llm.structured(purpose="sorgu", tier="query", system="S", user="U", schema=Out, conn=conn)
    assert out.value == "ok"
    assert sent["url"] == "https://ornek.ai/v1/chat/completions" and sent["auth"] == "Bearer k"
    assert sent["body"]["response_format"]["type"] == "json_schema"
    assert tuple(conn.execute("SELECT model, input_tokens FROM llm_calls").fetchone()) == ("openai:glm-4.5-flash", 30)


def test_openai_compatible_falls_back_to_json_mode(monkeypatch):
    _use_openai(monkeypatch)
    calls = []

    def urlopen(req, timeout):
        body = json.loads(req.data)
        calls.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            raise llm.urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"unsupported"))
        assert "JSON şemasına" in body["messages"][0]["content"]
        return _openai_reply('```json\n{"value": "ok"}\n```')
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    assert llm.structured(purpose="s", tier="query", system="S", user="U", schema=Out).value == "ok"
    assert calls == ["json_schema", "json_object"]


# --- Model zinciri / Gemini / BYOK ---------------------------------------------

SECRET = "SIR-ANAHTAR-123"


def _chain(monkeypatch, value, **extra):
    from kys.config import parse_chain
    monkeypatch.setattr(llm, "settings", dataclasses.replace(
        llm.settings, model_query=parse_chain(value), gemini_api_key=extra.pop("gemini_api_key", "g-env"), **extra))


def _http_error(req, code, body=b"hata"):
    return llm.urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(body))


def test_parse_chain_single_and_multiple():
    from kys.config import DEFAULT_QUERY_CHAIN, parse_chain
    assert parse_chain("anthropic:claude-haiku-5-5") == (ModelSpec("anthropic", "claude-haiku-5-5"),)
    chain = parse_chain(DEFAULT_QUERY_CHAIN)
    assert [m.provider for m in chain] == ["gemini", "gemini", "anthropic"]


def test_chain_falls_through_on_503_and_logs_each_attempt(conn, monkeypatch):
    _chain(monkeypatch, "gemini:m1,gemini:m2")
    seen = []

    def urlopen(req, timeout):
        body = json.loads(req.data)
        seen.append((req.full_url, body["model"], req.get_header("Authorization")))
        if body["model"] == "m1":
            raise _http_error(req, 503)
        return _openai_reply('{"value": "ok"}')
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    out = llm.structured(purpose="sorgu", tier="query", system="S", user="U", schema=Out, conn=conn)
    assert out.value == "ok" and llm.last_model.get() == "gemini:m2"
    assert seen[0][0] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert seen[0][2] == "Bearer g-env"
    rows = conn.execute("SELECT model, ok, error FROM llm_calls ORDER BY id").fetchall()
    assert [(r["model"], r["ok"]) for r in rows] == [("gemini:m1", 0), ("gemini:m2", 1)]
    assert "503" in rows[0]["error"]


def test_chain_skips_provider_without_key_and_permanent_errors(conn, monkeypatch):
    _chain(monkeypatch, "gemini:m1,openai:x,anthropic:h", gemini_api_key="", openai_base_url="https://o.ai/v1")

    def urlopen(req, timeout):
        raise _http_error(req, 403)
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(messages=SimpleNamespace(
        parse=lambda **kw: _resp(parsed=Out(value="son")))))
    assert llm.structured(purpose="s", tier="query", system="S", user="U", schema=Out, conn=conn).value == "son"
    errs = [(r["model"], r["ok"], r["error"]) for r in conn.execute("SELECT * FROM llm_calls ORDER BY id")]
    assert errs[0][0] == "gemini:m1" and "GEMINI_API_KEY" in errs[0][2]
    assert errs[1][0] == "openai:x" and "403" in errs[1][2]
    assert errs[2][:2] == ("anthropic:h", 1)


def test_chain_exhausted_raises_unavailable_with_summary(conn, monkeypatch):
    _chain(monkeypatch, "gemini:m1,gemini:m2")

    def urlopen(req, timeout):
        raise _http_error(req, 429, b"kota")
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    with pytest.raises(llm.LLMUnavailable) as ei:
        llm.structured(purpose="sorgu", tier="query", system="S", user="U", schema=Out, conn=conn)
    assert isinstance(ei.value, llm.LLMError)
    assert "gemini:m1" in str(ei.value) and "gemini:m2" in str(ei.value) and "429" in str(ei.value)
    assert conn.execute("SELECT COUNT(*) FROM llm_calls WHERE ok = 0").fetchone()[0] == 2


def test_gemini_json_schema_400_falls_back_to_json_mode(monkeypatch):
    _chain(monkeypatch, "gemini:m1")
    kinds = []

    def urlopen(req, timeout):
        kind = json.loads(req.data)["response_format"]["type"]
        kinds.append(kind)
        if kind == "json_schema":
            raise _http_error(req, 400)
        return _openai_reply('{"value": "ok"}')
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    assert llm.structured(purpose="s", tier="query", system="S", user="U", schema=Out).value == "ok"
    assert kinds == ["json_schema", "json_object"]


def test_byok_uses_user_key_only_for_that_provider_and_never_logs_it(conn, monkeypatch, caplog):
    _chain(monkeypatch, "anthropic:h1,gemini:m1,gemini:m2")
    auths = []

    def urlopen(req, timeout):
        auths.append(req.get_header("Authorization"))
        # Sağlayıcı hata gövdesinde anahtarı yankılasa bile loga/hataya girmemeli.
        raise _http_error(req, 401, f"invalid key {SECRET}".encode())
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    with caplog.at_level("DEBUG"), pytest.raises(llm.LLMUnavailable) as ei:
        llm.structured(purpose="sorgu", tier="query", system="S", user="U", schema=Out, conn=conn,
                       byok=("gemini", SECRET))
    assert auths == [f"Bearer {SECRET}"] * 2  # yalnızca gemini modelleri, kullanıcı anahtarıyla
    assert SECRET not in str(ei.value) and SECRET not in caplog.text
    assert SECRET not in json.dumps([tuple(r) for r in conn.execute("SELECT * FROM llm_calls")])


def test_byok_provider_not_in_chain(monkeypatch):
    _chain(monkeypatch, "gemini:m1")
    with pytest.raises(llm.LLMUnavailable, match="anthropic"):
        llm.structured(purpose="s", tier="query", system="S", user="U", schema=Out, byok=("anthropic", "k"))
