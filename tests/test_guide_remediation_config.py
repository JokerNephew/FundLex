"""FL-D452/FL-D449 boundary tests for public guide configuration and caps."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fundlex.guide_generation.api import register_guide_generation_routes
from fundlex.guide_generation.model_router import _ObservationOnlyBudget
from fundlex.guide_generation.pipeline import PipelineConfig
from fundlex.guide_generation.service import (sanitize_public_config,
                                               _server_corpus_dir)
from fundlex.guide_generation.store import GuideGenerationStore
from fundlex.guide_generation.vector import DenseRetriever, build_dense_retriever
from fundlex.model_budget import BudgetError
from fundlex.store import RunStore

from guide_generation_fakes import FakeGuideRouter
from test_guide_generation_pipeline import _regulation


def _app(tmp_path):
    store = RunStore(tmp_path / "state")
    gg = GuideGenerationStore(store)
    application = FastAPI()
    register_guide_generation_routes(application, store, gg, lambda: "member")
    return store, gg, TestClient(application)


def _post_guide(client, tmp_path, config):
    regulation = tmp_path / "regulation.docx"
    _regulation(regulation)
    return client.post(
        "/api/guide-generation/runs",
        files={"file": ("regulation.docx", regulation.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"config": json.dumps(config)})


@pytest.mark.parametrize("config", [
    {"vector_enabled": True, "vector_embedding_base_url": "https://sentinel.invalid/v1"},
    {"vector_embedding_model": "sentinel-model", "vector_embedding_api_key_env": "SENTINEL_KEY"},
    {"vector_qdrant_url": "https://sentinel.invalid:6333", "vector_qdrant_api_key_env": "SENTINEL_KEY"},
    {"vector_index_path": "/tmp/sentinel-index.sqlite3"},
    {"corpus_dir": "/etc"},
    {"corpus_dir": "../outside"},
    {"sample_contract": "/tmp/sentinel.docx"},
    {"soft_max_calls": 1},
    {"soft_max_cost": 0.0001},
    {"unknown_field": True},
])
def test_member_transport_and_path_config_is_rejected(tmp_path, config):
    store, gg, client = _app(tmp_path)
    response = _post_guide(client, tmp_path, config)
    assert response.status_code == 422, response.text
    assert "CONFIG_FIELD_FORBIDDEN" in response.text
    assert gg.list_runs("member") == []


def test_malicious_vector_config_never_reaches_authorization(tmp_path, monkeypatch):
    sentinel = "SENTINEL-AUTH-MUST-NOT-ESCAPE"
    seen_headers: list[dict] = []

    def fake_post(*args, **kwargs):
        seen_headers.append(dict(kwargs.get("headers") or {}))
        raise AssertionError("vector transport must not be called for a rejected config")

    monkeypatch.setattr("fundlex.guide_generation.vector.httpx.post", fake_post)
    store, gg, client = _app(tmp_path)
    response = _post_guide(client, tmp_path, {
        "vector_enabled": True,
        "vector_embedding_base_url": "https://sentinel.invalid/v1",
        "vector_embedding_model": "sentinel-model",
        "vector_embedding_api_key_env": "SENTINEL_KEY",
        "vector_qdrant_url": "https://sentinel.invalid:6333",
    })
    assert response.status_code == 422
    assert gg.list_runs("member") == []
    assert seen_headers == []
    assert sentinel not in json.dumps(seen_headers)


def test_legal_member_config_and_server_dense_transport(tmp_path):
    clean = sanitize_public_config({
        "corpus_limit": 2,
        "path_b_latest_only": False,
        "semantic_applicability": False,
        "max_residual_rounds": 2,
        "guide_scope_sections": ["基金费用与税收"],
        "corpus_dir": "funds_word",  # alias only; the server picks the root
    })
    assert clean["corpus_limit"] == 2
    assert clean["path_b_latest_only"] is False
    assert clean["guide_scope_sections"] == ["基金费用与税收"]
    assert "corpus_dir" not in clean
    assert _server_corpus_dir().endswith("funds_word")

    config = PipelineConfig(
        vector_enabled=True,
        vector_embedding_base_url="https://embedding.internal.example/v1",
        vector_embedding_model="legal-embedding",
        vector_index_path="vectors/index.sqlite3",
    )
    retriever = build_dense_retriever(config, tmp_path)
    assert isinstance(retriever, DenseRetriever)
    assert retriever.index.path.resolve().is_relative_to(tmp_path.resolve())

    with pytest.raises(Exception):
        build_dense_retriever(
            PipelineConfig(vector_enabled=True,
                           vector_embedding_base_url="https://embedding.internal.example/v1",
                           vector_embedding_model="legal-embedding",
                           vector_index_path="/tmp/outside.sqlite3"), tmp_path)


class _CapBudget:
    concurrency = 2
    max_requests = 1
    max_cost_usd = 1.0

    def reserve(self, **_kwargs):
        raise BudgetError("MODEL_GLOBAL_CALL_BUDGET_EXCEEDED")

    def estimate(self, input_tokens, output_tokens):
        return (input_tokens + output_tokens) / 1_000_000

    def finish(self, *_args, **_kwargs):
        raise AssertionError("no ledger row for an observation-only call")

    def snapshot(self):
        return {}


class _ConcurrencyBudget(_CapBudget):
    def reserve(self, **_kwargs):
        raise BudgetError("MODEL_CONCURRENCY_LIMIT")


def test_cost_and_request_caps_are_observation_only_but_concurrency_is_kept():
    wrapped = _ObservationOnlyBudget(_CapBudget())
    token = wrapped.reserve(input_token_bound=10, output_token_bound=5, lease_seconds=10)
    assert token.startswith("observation:")
    assert wrapped.finish(token, {}, prompt_tokens=10, completion_tokens=5, success=True) > 0
    with pytest.raises(BudgetError, match="MODEL_CONCURRENCY_LIMIT"):
        _ObservationOnlyBudget(_ConcurrencyBudget()).reserve(
            input_token_bound=1, output_token_bound=1, lease_seconds=1)


def test_service_defaults_do_not_inject_soft_caps():
    from fundlex.guide_generation.service import _config
    payload = _config({})
    assert "soft_max_calls" not in payload
    assert "soft_max_cost" not in payload
    assert payload["corpus_dir"] == _server_corpus_dir()


class _FakeGateway:
    max_calls = 1
    max_context_chars = 32000
    model = "fake"
    provider = "fake"

    def call(self, **_kwargs):
        from fundlex.model import ModelResult
        return ModelResult({"ok": True}, "fake", 1, 1, 1, 2, None, 1, 0.0, "t", "ctx")


def test_router_removes_cumulative_call_cap_and_soft_caps():
    from fundlex.guide_generation.model_router import GuideModelRouter
    router = GuideModelRouter({"primary": _FakeGateway()})
    assert router.run_max_calls is None
    assert router.run_max_cost is None
    assert router.gateways["primary"].max_calls == float("inf")


def test_residual_per_round_call_cap_is_observation_only():
    from fundlex.guide_generation.models import ClauseUnit, ContractVersion, PolicyRequirement
    from fundlex.guide_generation.residual import ResidualConfig, run_residual_mining

    requirement = PolicyRequirement(
        requirement_id="R-residual", source_block_ids=["B-residual"],
        source_quote="基金管理人应当调整费用。", article="第一条",
        norm_type="obligation", subject="基金管理人", object="费用",
        requirement="费用要求。", disposition="modify_contract")
    version = ContractVersion("CV-residual", "C-residual", "测试基金", "测试合同",
                              latest_known_version=True)
    clause_one = ClauseUnit("CL-residual-1", "CV-residual", ["费用"], 1, 1, "基金管理人收取申购费。")
    clause_two = ClauseUnit("CL-residual-2", "CV-residual", ["费用"], 2, 2, "基金管理人收取赎回费。")
    result = run_residual_mining(
        FakeGuideRouter(), [requirement], [], [], [version],
        {"CV-residual": [clause_one, clause_two]},
        {clause_one.clause_id: clause_one, clause_two.clause_id: clause_two},
        [{"contract_version_id": "CV-residual", "clause_ids": [clause_one.clause_id],
          "requirement_ids": [requirement.requirement_id], "status": "affected"},
         {"contract_version_id": "CV-residual", "clause_ids": [clause_two.clause_id],
          "requirement_ids": [requirement.requirement_id], "status": "affected"}],
        config=ResidualConfig(max_rounds=1, required_clean_rounds=1, batch_chars=10,
                              max_calls_per_round=1))
    assert result.calls >= 2
    assert result.saturated is True


def test_pipeline_ignores_soft_caps_and_scans_every_clause_batch(tmp_path):
    from fundlex.guide_generation.discovery import DiscoveryConfig, path_b_contract_sweep
    from fundlex.guide_generation.models import ClauseUnit, ContractVersion, PolicyRequirement
    from fundlex.guide_generation.pipeline import GuidePipeline
    from test_guide_generation_pipeline import _prepare

    store, gg, run_id, corpus = _prepare(tmp_path)
    pipeline = GuidePipeline(gg, run_id, FakeGuideRouter(),
                             PipelineConfig(corpus_dir=str(corpus), path_b_latest_only=False,
                                            path_c_enabled=False, semantic_applicability=False,
                                            max_residual_rounds=2, soft_max_calls=1,
                                            soft_max_cost=0.000001))
    assert pipeline.router.run_max_calls is None
    assert pipeline.router.run_max_cost is None
    assert pipeline.run()["qualification_status"] == "candidate_ready"

    requirements = [PolicyRequirement(
        requirement_id="R-policy", source_block_ids=["B-policy"],
        source_quote="基金管理人应当调整费用。", article="第一条",
        norm_type="obligation", subject="基金管理人", object="费用",
        requirement="费用要求。", disposition="modify_contract")]
    versions = [ContractVersion("CV-policy", "C-policy", "测试基金", "测试合同",
                                latest_known_version=True)]
    clauses = {
        "CV-policy": [
            ClauseUnit("CL-policy-1", "CV-policy", ["费用"], 1, 1, "基金管理人收取申购费。"),
            ClauseUnit("CL-policy-2", "CV-policy", ["费用"], 2, 2, "基金管理人收取赎回费。"),
        ]}
    impacts, _suspicions, evidence, calls = path_b_contract_sweep(
        FakeGuideRouter(), None,
        requirements, versions, clauses,
        DiscoveryConfig(path_b_batch_chars=10, path_b_max_requirements=1,
                        path_b_max_calls=1, path_c_enabled=False),
        max_workers=1)
    assert len(evidence) >= 2
    assert calls == len(evidence)

