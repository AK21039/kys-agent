import argparse
import dataclasses

from kys import cli, config


def test_scheduled_ingest_uses_inbox_dir_and_all_flags(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(config, "LOCAL_HOME", tmp_path)
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, inbox_dir=tmp_path / "inbox"))
    monkeypatch.setattr(cli, "cmd_ingest", lambda a: seen.setdefault("ingest", a))
    monkeypatch.setattr(cli, "cmd_classify", lambda a: seen.setdefault("classify", a))

    cli.cmd_scheduled(argparse.Namespace(limit=None))

    ingest = seen["ingest"]
    assert ingest.path == str(tmp_path / "inbox")
    # cmd_ingest'in okuduğu her bayrak verilmiş olmalı (eksik bayrak zamanlanmış işi çökertir)
    assert ingest.no_llm is True and ingest.no_ocr is False
    assert list((tmp_path / "logs").glob("zamanli-*.log"))
