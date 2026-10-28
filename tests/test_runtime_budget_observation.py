"""Runtime policy FL-D445/FL-D449: legacy caps are observations, not stop gates.

The deployment environment keeps historical values such as
``FUNDLEX_MODEL_MAX_REQUESTS=40000``, ``FUNDLEX_MODEL_MAX_COST_USD=50`` and
``FUNDLEX_MODEL_MAX_CALLS=192``. Those values must not pause or reject calls after
this change. Only the explicit ``FUNDLEX_MODEL_ENFORCE_LIMITS=1`` test switch
restores the old hard caps. Concurrency, the circuit breaker and finite technical
retries remain hard safety boundaries.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from fundlex.model import ModelError, ModelGateway
from fundlex.model_budget import BudgetError, ModelBudget


def _response(value: dict) -> httpx.Response:
    return httpx.Response(200, json={
        "model": "actual-model",
        "choices": [{"message": {"content": json.dumps(value)}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    })


def _gateway(path: Path, budget: ModelBudget | None = None, *, max_calls: int = 16,
             enforce_calls: bool = False, handler=None) -> ModelGateway:
    handler = handler or (lambda _: _response({"quote": "混合型", "fund_type": "ordinary"}))
    return ModelGateway(base_url="https://model.invalid", model="test", api_key="never-log-this",
                        client=httpx.Client(transport=httpx.MockTransport(handler)),
                        budget=budget, retries=0, max_calls=max_calls,
                        enforce_calls=enforce_calls)


def _set_env(monkeypatch: pytest.MonkeyPatch, path: Path, *, requests: str,
             cost: str, calls: str | None = None, enforce: str = "0") -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://model.invalid")
    monkeypatch.setenv("LLM_MODEL", "test")
    monkeypatch.setenv("LLM_API_KEY", "never-log-this")
    monkeypatch.setenv("FUNDLEX_MODEL_LEDGER", str(path))
    monkeypatch.setenv("FUNDLEX_MODEL_MAX_REQUESTS", requests)
    monkeypatch.setenv("FUNDLEX_MODEL_MAX_COST_USD", cost)
    monkeypatch.setenv("FUNDLEX_MODEL_ENFORCE_LIMITS", enforce)
    if calls is not None:
        monkeypatch.setenv("FUNDLEX_MODEL_MAX_CALLS", calls)
    else:
        monkeypatch.delenv("FUNDLEX_MODEL_MAX_CALLS", raising=False)


def _use_mock_transport(gateway: ModelGateway) -> ModelGateway:
    gateway._client.close()
    gateway._client = httpx.Client(
        transport=httpx.MockTransport(lambda _: _response({"quote": "混合型", "fund_type": "ordinary"})))
    return gateway


def test_production_legacy_env_values_are_parsed_as_observations(tmp_path, monkeypatch):
    """The exact production values remain visible but cannot reject a call."""
    _set_env(monkeypatch, tmp_path / "ledger.sqlite", requests="40000", cost="50", calls="192")
    gateway = _use_mock_transport(ModelGateway.from_env())
    assert gateway.max_calls == 192 and gateway.enforce_calls is False
    snapshot = gateway.budget.snapshot()
    assert snapshot["max_http_attempts"] == 40000
    assert snapshot["max_cost_usd"] == 50.0
    assert snapshot["request_cap_enforced"] is False and snapshot["cost_cap_enforced"] is False
    assert gateway.extract_fund_type("混合型证券投资基金").model == "actual-model"


def test_small_legacy_env_limits_do_not_block_or_pause(tmp_path, monkeypatch):
    """A pre-existing tiny limit is still observation-only after deployment."""
    _set_env(monkeypatch, tmp_path / "ledger.sqlite", requests="1", cost="0.000001", calls="1")
    gateway = _use_mock_transport(ModelGateway.from_env())
    assert gateway.extract_fund_type("混合型证券投资基金").model == "actual-model"
    assert gateway.extract_fund_type("混合型证券投资基金").model == "actual-model"
    snapshot = gateway.budget.snapshot()
    assert snapshot["http_attempts"] == 2
    assert snapshot["request_cap_exceeded"] is True
    assert snapshot["cost_cap_exceeded"] is True
    metrics = gateway.metrics()
    assert metrics["logical_calls"] == 2
    assert metrics["call_reference_exceeded"] is True
    assert metrics["call_cap_enforced"] is False


def test_env_enforcement_switch_restores_legacy_cap_for_tests(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path / "ledger.sqlite", requests="10", cost="1", calls="1",
             enforce="1")
    gateway = _use_mock_transport(ModelGateway.from_env())
    assert gateway.enforce_calls is True
    assert gateway.extract_fund_type("混合型证券投资基金").model == "actual-model"
    with pytest.raises(ModelError, match="MODEL_CALL_BUDGET_EXCEEDED"):
        gateway.extract_fund_type("混合型证券投资基金")


def test_gateway_call_reference_is_observational_by_default(tmp_path):
    gateway = _gateway(tmp_path / "ledger.sqlite", max_calls=1)
    assert gateway.extract_fund_type("混合型证券投资基金").model == "actual-model"
    assert gateway.extract_fund_type("混合型证券投资基金").model == "actual-model"
    metrics = gateway.metrics()
    assert metrics["logical_calls"] == 2 and metrics["call_reference_exceeded"] is True
    assert metrics["call_cap_enforced"] is False


def test_gateway_explicit_call_enforcement_rejects_zero_and_honours_cap(tmp_path):
    with pytest.raises(ModelError, match="MODEL_CALL_CAP_INVALID"):
        _gateway(tmp_path / "zero.sqlite", max_calls=0, enforce_calls=True)
    gateway = _gateway(tmp_path / "ledger.sqlite", max_calls=1, enforce_calls=True)
    assert gateway.extract_fund_type("混合型证券投资基金").model == "actual-model"
    with pytest.raises(ModelError, match="MODEL_CALL_BUDGET_EXCEEDED"):
        gateway.extract_fund_type("混合型证券投资基金")


def test_concurrency_and_circuit_breaker_remain_hard_boundaries(tmp_path):
    budget = ModelBudget(tmp_path / "ledger.sqlite", max_requests=1000, max_cost_usd=100,
                         concurrency=1)
    reservation = budget.reserve(input_token_bound=100, output_token_bound=10, lease_seconds=30)
    with pytest.raises(BudgetError, match="MODEL_CONCURRENCY_LIMIT"):
        budget.reserve(input_token_bound=100, output_token_bound=10, lease_seconds=30)
    budget.finish(reservation, {}, prompt_tokens=100, completion_tokens=10, success=True)
    circuit = ModelBudget(tmp_path / "circuit.sqlite", max_requests=1000, max_cost_usd=100)
    for _ in range(3):
        gateway = _gateway(tmp_path / "circuit.sqlite", circuit,
                           handler=lambda _: httpx.Response(503))
        with pytest.raises(ModelError, match="MODEL_RETRY_EXHAUSTED"):
            gateway.extract_fund_type("混合型证券投资基金")
    gateway = _gateway(tmp_path / "circuit.sqlite", circuit,
                       handler=lambda _: pytest.fail("circuit must stop transport"))
    with pytest.raises(ModelError, match="MODEL_CIRCUIT_OPEN"):
        gateway.extract_fund_type("混合型证券投资基金")


def test_ledger_records_exact_attempts_and_tokens_beyond_reference(tmp_path):
    budget = ModelBudget(tmp_path / "ledger.sqlite", max_requests=1, max_cost_usd=1)
    for _ in range(3):
        gateway = _gateway(tmp_path / "ledger.sqlite", budget, max_calls=1)
        assert gateway.extract_fund_type("混合型证券投资基金").model == "actual-model"
    snapshot = budget.snapshot()
    assert snapshot["http_attempts"] == 3
    assert snapshot["statuses"] == {"completed": 3}
    assert snapshot["cost_is_provider_invoice"] is False
