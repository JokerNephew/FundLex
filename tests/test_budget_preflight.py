"""Offline admission tests for the evaluation budget guard."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from tools.evaluation.budget_preflight import (
    PreflightError,
    StartupPlan,
    guarded_start,
    ledger_anchor,
    preflight,
)


def _ledger(path: Path, rows: int = 0, cost: str = "0") -> None:
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE requests (
            id TEXT PRIMARY KEY, started REAL NOT NULL, lease_until REAL NOT NULL,
            status TEXT NOT NULL, reserved_cost REAL NOT NULL, charged_cost REAL NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}')""")
        each = float(cost) / rows if rows else 0.0
        for number in range(rows):
            db.execute("INSERT INTO requests VALUES (?, ?, ?, 'completed', ?, ?, '{}')",
                       (f"r{number}", number, number + 1, each, each))


def _inputs(root: Path) -> tuple[Path, Path]:
    selection = root / "selection.json"
    selection.write_text(json.dumps({"cases": [{"case_id": "D01"}]}), encoding="utf-8")
    labels = root / "labels.json"
    labels.write_text('{"D01": []}\n', encoding="utf-8")
    return selection, labels


def _protocol(root: Path, ledger: Path, selection: Path, labels: Path,
              monkeypatch: pytest.MonkeyPatch,
              *, max_requests: int = 16, max_cost: str = "1") -> tuple[Path, StartupPlan]:
    plan = StartupPlan("eval-01", selection, labels, ("D01",), 2, "0.2")
    # Resolve the same engine identity used by the actual startup snapshot.
    from tools.evaluation.budget_preflight import _startup
    monkeypatch.setenv("FUNDLEX_MODEL_LEDGER", str(ledger))
    actual, _ = _startup(plan)
    actual["budget"]["max_requests"] = max_requests
    actual["budget"]["max_cost_usd"] = max_cost
    actual["budget"]["ledger_path"] = str(ledger.resolve())
    protocol = {"schema": "fundlex-evaluation-budget-v1", "authorization_id": "auth-01",
                "config": actual, "ledger_anchor": ledger_anchor(ledger)}
    path = root / "protocol.json"
    path.write_text(json.dumps(protocol, sort_keys=True, indent=2), encoding="utf-8")
    return path, plan


@pytest.fixture(autouse=True)
def _clean_budget_env(monkeypatch):
    monkeypatch.setenv("FUNDLEX_MODEL_MODE", "live")
    monkeypatch.delenv("FUNDLEX_MODEL_LEDGER", raising=False)
    monkeypatch.delenv("FUNDLEX_MODEL_MAX_REQUESTS", raising=False)
    monkeypatch.delenv("FUNDLEX_MODEL_MAX_COST_USD", raising=False)
    monkeypatch.delenv("FUNDLEX_MODEL_CONCURRENCY", raising=False)


def _run(root: Path, *, ledger_rows: int = 0, ledger_cost: str = "0",
         max_requests: int = 16, max_cost: str = "1",
         monkeypatch: pytest.MonkeyPatch) -> tuple[Path, StartupPlan, Path]:
    ledger = root / "ledger.sqlite"
    _ledger(ledger, ledger_rows, ledger_cost)
    selection, labels = _inputs(root)
    protocol, plan = _protocol(root, ledger, selection, labels, monkeypatch,
                                max_requests=max_requests, max_cost=max_cost)
    manifest = root / "preflight.json"
    return protocol, plan, manifest


def _invoke(protocol: Path, plan: StartupPlan, manifest: Path):
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    return preflight(protocol, protocol_sha256=digest, plan=plan, manifest_path=manifest)


def test_valid_fixture_passes_and_manifest_is_safe(tmp_path: Path, monkeypatch):
    protocol, plan, manifest = _run(tmp_path, monkeypatch=monkeypatch)
    result = _invoke(protocol, plan, manifest)
    text = manifest.read_text(encoding="utf-8")
    assert result["status"] == "PREFLIGHT_PASSED"
    assert "api_key" not in text and "base_url" not in text and "http://" not in text
    assert result["evidence"]["required_requests"] == 2


def test_existing_usage_over_cap_fails_closed(tmp_path: Path, monkeypatch):
    protocol, plan, manifest = _run(tmp_path, ledger_rows=17, ledger_cost="1.1", monkeypatch=monkeypatch)
    with pytest.raises(PreflightError, match="LEDGER_ALREADY_OVER_CAP"):
        _invoke(protocol, plan, manifest)
    assert not manifest.exists()


def test_different_ledger_cannot_bypass_history(tmp_path: Path, monkeypatch):
    protocol, plan, manifest = _run(tmp_path, ledger_rows=1, ledger_cost="0.1", monkeypatch=monkeypatch)
    other = tmp_path / "other.sqlite"
    _ledger(other)
    monkeypatch.setenv("FUNDLEX_MODEL_LEDGER", str(other))
    with pytest.raises(PreflightError, match="CONFIG_MISMATCH:budget.ledger_path"):
        _invoke(protocol, plan, manifest)


def test_runtime_cap_override_is_rejected(tmp_path: Path, monkeypatch):
    protocol, plan, manifest = _run(tmp_path, monkeypatch=monkeypatch)
    monkeypatch.setenv("FUNDLEX_MODEL_MAX_REQUESTS", "5000")
    with pytest.raises(PreflightError, match="CONFIG_MISMATCH:budget.max_requests"):
        _invoke(protocol, plan, manifest)


@pytest.mark.parametrize(("name", "value", "field"), [
    ("FUNDLEX_MODEL_MAX_COST_USD", "5", "max_cost_usd"),
    ("FUNDLEX_MODEL_CONCURRENCY", "2", "concurrency"),
])
def test_runtime_budget_overrides_are_rejected(tmp_path: Path, monkeypatch,
                                               name: str, value: str, field: str):
    protocol, plan, manifest = _run(tmp_path, monkeypatch=monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(PreflightError, match=f"CONFIG_MISMATCH:budget.{field}"):
        _invoke(protocol, plan, manifest)


def test_runtime_role_cap_override_is_rejected(tmp_path: Path, monkeypatch):
    protocol, plan, manifest = _run(tmp_path, monkeypatch=monkeypatch)
    monkeypatch.setenv("FUNDLEX_PRIMARY_MAX_CALLS", "99")
    with pytest.raises(PreflightError, match="CONFIG_MISMATCH:case_budget.max_calls"):
        _invoke(protocol, plan, manifest)


def test_case_allowance_must_fit_remaining_balance(tmp_path: Path, monkeypatch):
    protocol, plan, manifest = _run(tmp_path, ledger_rows=15, ledger_cost="0.15",
                                    monkeypatch=monkeypatch)
    with pytest.raises(PreflightError, match="INSUFFICIENT_RUN_BALANCE"):
        _invoke(protocol, plan, manifest)


def test_existing_manifest_is_never_overwritten(tmp_path: Path, monkeypatch):
    protocol, plan, manifest = _run(tmp_path, monkeypatch=monkeypatch)
    manifest.write_text("sentinel\n", encoding="utf-8")
    with pytest.raises(PreflightError, match="MANIFEST_ALREADY_EXISTS"):
        _invoke(protocol, plan, manifest)
    assert manifest.read_text(encoding="utf-8") == "sentinel\n"


def test_missing_labels_hash_evidence_fails_before_callback(tmp_path: Path, monkeypatch):
    protocol, plan, manifest = _run(tmp_path, monkeypatch=monkeypatch)
    plan = StartupPlan(plan.run_id, plan.selection, tmp_path / "missing-labels.json",
                       plan.case_ids, plan.requests_per_case, plan.cost_per_case_usd)
    called = []
    with pytest.raises(PreflightError, match="UNREADABLE:labels"):
        guarded_start(protocol, protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),
                      plan=plan, manifest_path=manifest,
                      start=lambda env: called.append(env))
    assert called == []


def test_protocol_without_labels_hash_fails_closed(tmp_path: Path, monkeypatch):
    protocol, plan, manifest = _run(tmp_path, monkeypatch=monkeypatch)
    protocol_data = json.loads(protocol.read_text(encoding="utf-8"))
    del protocol_data["config"]["labels_sha256"]
    protocol.write_text(json.dumps(protocol_data), encoding="utf-8")
    with pytest.raises(PreflightError, match="SCHEMA:config"):
        _invoke(protocol, plan, manifest)
    assert not manifest.exists()


def test_missing_ledger_cannot_create_a_new_budget(tmp_path: Path, monkeypatch):
    protocol, plan, manifest = _run(tmp_path, monkeypatch=monkeypatch)
    missing = tmp_path / "new-ledger.sqlite"
    protocol_data = json.loads(protocol.read_text(encoding="utf-8"))
    protocol_data["config"]["budget"]["ledger_path"] = str(missing)
    protocol.write_text(json.dumps(protocol_data), encoding="utf-8")
    with pytest.raises(PreflightError):
        _invoke(protocol, plan, manifest)
    assert not missing.exists()
