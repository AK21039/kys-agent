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
