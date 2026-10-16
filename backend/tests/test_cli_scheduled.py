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


def _fake_gcloud(monkeypatch):
    import subprocess
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setattr("kys.cloudpublish.subprocess.run", run)
    return calls


def test_cloudpublish_upload_uses_powershell_and_restarts(tmp_path, monkeypatch):
    from kys import cloudpublish
    calls = _fake_gcloud(monkeypatch)
    (tmp_path / "pages").mkdir()
    db = tmp_path / "kys-query.db"
    db.write_bytes(b"x")
    cloudpublish.upload(db, tmp_path / "pages", "gs://b'x", service="kys-qa", region="europe-west1")
    assert len(calls) == 3
    assert all("cmd" not in c[0].lower() or "powershell" in c[0].lower() for c in calls)
    assert all(c[1:3] == ["-NoProfile", "-NonInteractive"] for c in calls)
    assert "'storage' 'cp'" in calls[0][-1] and "gs://b''x/kys.db" in calls[0][-1]
    assert "'storage' 'rsync'" in calls[1][-1]
    assert "'run' 'services' 'update' 'kys-qa'" in calls[2][-1] and "KYS_DB_REV=" in calls[2][-1]


def test_cloudpublish_failure_raises(monkeypatch):
    import subprocess
    import pytest
    from kys import cloudpublish
    monkeypatch.setattr("kys.cloudpublish.subprocess.run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="izin yok"))
    with pytest.raises(RuntimeError, match="izin yok"):
        cloudpublish.gcloud("storage", "ls")


def test_scheduled_publishes_when_bucket_set_and_survives_upload_error(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(config, "LOCAL_HOME", tmp_path)
    monkeypatch.setattr(config, "settings", dataclasses.replace(
        config.settings, inbox_dir=tmp_path / "inbox", publish_bucket="gs://kova"))
    monkeypatch.setattr(cli, "cmd_ingest", lambda a: None)
    monkeypatch.setattr(cli, "cmd_classify", lambda a: None)

    def boom(a):
        seen["publish"] = a
        raise RuntimeError("ağ yok")
    monkeypatch.setattr(cli, "cmd_publish", boom)

    cli.cmd_scheduled(argparse.Namespace(limit=None))  # istisna fırlatmamalı

    assert seen["publish"].upload == "gs://kova" and seen["publish"].pages == ""
    assert "ağ yok" in next((tmp_path / "logs").glob("zamanli-*.log")).read_text(encoding="utf-8")


def test_scheduled_skips_publish_without_bucket(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_HOME", tmp_path)
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, inbox_dir=tmp_path / "i", publish_bucket=""))
    monkeypatch.setattr(cli, "cmd_ingest", lambda a: None)
    monkeypatch.setattr(cli, "cmd_classify", lambda a: None)
    monkeypatch.setattr(cli, "cmd_publish", lambda a: (_ for _ in ()).throw(AssertionError("çağrılmamalı")))
    cli.cmd_scheduled(argparse.Namespace(limit=None))
