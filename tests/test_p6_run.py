"""Admission ordering checks for the real-path P6 launcher."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.evaluation import p6_run
from tools.evaluation.budget_preflight import PreflightError


def test_preflight_rejection_happens_before_account_http_or_run_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps({"cases": [{"case_id": "D01", "group": "dev", "file": "D01.docx", "sha256": "0" * 64}]}),
        encoding="utf-8",
    )
    output_root = tmp_path / "runs"
    manifest = tmp_path / "preflight.json"
    http_constructed = []

    def reject(*_args, **_kwargs):
        raise PreflightError("LEDGER_ALREADY_OVER_CAP")

    class UnexpectedClient:
        def __init__(self, *_args, **_kwargs):
            http_constructed.append(True)
            raise AssertionError("HTTP must not be constructed before admission")

    monkeypatch.setattr(p6_run, "preflight", reject)
    monkeypatch.setattr(p6_run.httpx, "Client", UnexpectedClient)
    monkeypatch.setattr(
        p6_run.secrets,
        "choice",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("account credentials must not be generated before admission")
        ),
    )
    monkeypatch.setattr(
        p6_run.secrets,
        "token_urlsafe",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("account credentials must not be generated before admission")
        ),
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "p6_run",
            "--selection",
            str(selection),
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--run-id",
            "eval-rejected",
            "--group",
            "dev",
            "--preflight-protocol",
            str(tmp_path / "protocol.json"),
            "--preflight-protocol-sha256",
            "a" * 64,
            "--preflight-manifest",
            str(manifest),
            "--labels",
            str(tmp_path / "labels.json"),
            "--requests-per-case",
            "2",
            "--cost-per-case-usd",
            "0.2",
        ],
    )
    assert p6_run.main() == 2
    assert "PREFLIGHT_REJECTED:LEDGER_ALREADY_OVER_CAP" in capsys.readouterr().out
    assert not output_root.exists()
    assert not manifest.exists()
    assert http_constructed == []
