"""Primary / review role separation (plan §4).

The tests never touch the network: they exercise configuration resolution and the
dispatch wrapper with stub gateways.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fundlex.model import ModelResult
from fundlex.models.config import RoleConfigError, load_role_config
from fundlex.models.roles import (DEFAULT_TASK_ROLES, RoleGateway, build_role_gateway,
                                  role_for_task)


class StubGateway:
    def __init__(self, model: str, *, max_context_chars: int = 1000, fail: bool = False):
        self.model = model
        self.provider = "stub"
        self.max_context_chars = max_context_chars
        self.max_calls = 10
        self.calls: list[tuple[str, str]] = []
        self.events: list[dict] = []
        self.budget = None
        self.closed = False
        self.fail = fail
        self.bindings: list[tuple[Path, dict]] = []

    def call(self, *, task_type, bounded_context, response_schema, instruction,
             prompt_version="v1"):
        if self.fail:
            raise AssertionError("wrong role")
        self.calls.append((task_type, bounded_context))
        self.events.append({"task_type": task_type, "actual_model": self.model,
                            "prompt_tokens": 10, "completion_tokens": 5,
                            "total_tokens": 15, "estimated_cost_usd": 0.01,
                            "latency_ms": 3})
        return ModelResult({"ok": True}, self.model, 3, 10, 5, 15, None, 1,
                           task_type=task_type)

    def bind_checkpoints(self, directory, dependencies):
        self.bindings.append((Path(directory), dependencies))

    def metrics(self):
        return {"logical_calls": len(self.calls), "http_attempts": len(self.calls),
                "checkpoint_reuses": 0, "checkpoint_invalidations": 0,
                "prompt_tokens": 10 * len(self.calls),
                "completion_tokens": 5 * len(self.calls),
                "total_tokens": 15 * len(self.calls), "latency_ms": 3 * len(self.calls),
                "rate_limit_count": 0, "error_count": 0,
                "estimated_cost_usd": 0.01 * len(self.calls),
                "events": list(self.events)}

    def close(self):
        self.closed = True


def test_default_task_roles_keep_review_independent():
    assert role_for_task("recall_compose") == "primary"
    assert role_for_task("recall_facts") == "primary"
    assert role_for_task("recall_verify") == "review"
    assert role_for_task("recall_audit") == "review"
    assert role_for_task("recall_sweep") == "review"
    assert role_for_task("recall_arbitrate") == "review"
    # Unknown / legacy task types fall back to primary (safe default).
    assert role_for_task("legacy_task") == "primary"
    assert DEFAULT_TASK_ROLES["recall_joint_compose"] == "primary"


def test_role_gateway_routes_and_records_without_sharing_context():
    primary, review = StubGateway("primary-m"), StubGateway("review-m")
    gateway = RoleGateway(primary, review)

    gateway.call(task_type="recall_facts", bounded_context="source", response_schema={},
                 instruction="extract")
    gateway.call(task_type="recall_verify", bounded_context="before/after", response_schema={},
                 instruction="verify")

    assert [call[0] for call in primary.calls] == ["recall_facts"]
    assert [call[0] for call in review.calls] == ["recall_verify"]
    # The review role only receives the context the caller built for it.
    assert review.calls[0][1] == "before/after"
    assert [(c.role, c.task_type, c.model) for c in gateway.calls] == [
        ("primary", "recall_facts", "primary-m"),
        ("review", "recall_verify", "review-m"),
    ]
    metrics = gateway.metrics()
    assert metrics["logical_calls"] == 2
    assert metrics["roles"]["review"]["model"] == "review-m"
    assert {event["role"] for event in metrics["events"]} == {"primary", "review"}


def test_role_gateway_binds_checkpoints_per_role(tmp_path: Path):
    primary, review = StubGateway("primary-m"), StubGateway("review-m")
    gateway = RoleGateway(primary, review)
    gateway.bind_checkpoints(tmp_path, {"engine": "recall_first"})
    assert primary.bindings[0][1]["model_role"] == "primary"
    assert review.bindings[0][1]["model_role"] == "review"
    assert primary.bindings[0][1]["engine"] == "recall_first"
    assert primary.bindings[0][1]["task_roles_sha256"] != ""


def test_role_gateway_same_endpoint_uses_one_transport():
    shared = StubGateway("same-m")
    gateway = RoleGateway(shared, None)
    gateway.call(task_type="recall_compose", bounded_context="x", response_schema={},
                 instruction="compose")
    gateway.call(task_type="recall_audit", bounded_context="y", response_schema={},
                 instruction="audit")
    assert len(shared.calls) == 2
    assert [item.role for item in gateway.calls] == ["primary", "review"]
    assert gateway.roles["primary"]["same_endpoint_as_primary"] is True
    gateway.close()
    assert shared.closed


def _clear_role_env(monkeypatch: pytest.MonkeyPatch):
    for name in list(__import__("os").environ):
        if name.startswith("FUNDLEX_PRIMARY_") or name.startswith("FUNDLEX_REVIEW_") \
                or name.startswith("FUNDLEX_MODEL_ROLES") or name.startswith("LLM_"):
            monkeypatch.delenv(name, raising=False)


def test_review_role_inherits_primary_when_not_configured(monkeypatch: pytest.MonkeyPatch):
    _clear_role_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "model-x")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_API_KEY", "secret")
    configs, _ = load_role_config()
    assert configs["primary"].model == "model-x"
    assert configs["review"].model == "model-x"
    assert configs["review"].same_endpoint(configs["primary"])
    assert "secret" not in json.dumps(configs["review"].safe_dict())


def test_review_role_can_use_a_different_provider(monkeypatch: pytest.MonkeyPatch):
    _clear_role_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "model-a")
    monkeypatch.setenv("LLM_BASE_URL", "https://a.invalid/v1")
    monkeypatch.setenv("LLM_API_KEY", "key-a")
    monkeypatch.setenv("FUNDLEX_REVIEW_PROVIDER", "anthropic")
    monkeypatch.setenv("FUNDLEX_REVIEW_MODEL", "model-b")
    monkeypatch.setenv("FUNDLEX_REVIEW_BASE_URL", "https://b.invalid/v1")
    monkeypatch.setenv("FUNDLEX_REVIEW_API_KEY", "key-b")
    monkeypatch.setenv("FUNDLEX_REVIEW_TIMEOUT_S", "99")
    configs, _ = load_role_config()
    assert configs["primary"].model == "model-a"
    assert configs["review"].model == "model-b"
    assert configs["review"].provider == "anthropic"
    assert configs["review"].timeout_s == 99.0
    assert not configs["review"].same_endpoint(configs["primary"])


def test_partial_review_role_is_rejected(monkeypatch: pytest.MonkeyPatch):
    _clear_role_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "model-a")
    monkeypatch.setenv("LLM_BASE_URL", "https://a.invalid/v1")
    monkeypatch.setenv("LLM_API_KEY", "key-a")
    # Another endpoint without its own credential must never inherit the primary key.
    monkeypatch.setenv("FUNDLEX_REVIEW_BASE_URL", "https://b.invalid/v1")
    with pytest.raises(RoleConfigError, match="without its own API key"):
        load_role_config()


def test_review_can_override_only_the_model_on_the_primary_endpoint(
        monkeypatch: pytest.MonkeyPatch):
    _clear_role_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "model-a")
    monkeypatch.setenv("LLM_BASE_URL", "https://a.invalid/v1")
    monkeypatch.setenv("LLM_API_KEY", "key-a")
    monkeypatch.setenv("FUNDLEX_REVIEW_MODEL", "model-b")
    configs, _ = load_role_config()
    assert configs["review"].model == "model-b"
    assert configs["review"].base_url == configs["primary"].base_url
    assert configs["review"].api_key == configs["primary"].api_key


def test_role_file_supports_api_key_env_and_task_aliases(monkeypatch: pytest.MonkeyPatch,
                                                         tmp_path: Path):
    _clear_role_env(monkeypatch)
    path = tmp_path / "roles.json"
    path.write_text(json.dumps({
        "models": {
            "primary": {"provider": "p", "model": "a", "base_url": "https://a.invalid",
                        "api_key_env": "TEST_PRIMARY_KEY"},
            "review": {"provider": "q", "model": "b", "base_url": "https://b.invalid",
                       "api_key_env": "TEST_REVIEW_KEY", "max_tokens": 222},
        },
        "task_roles": {"compose_review": "review", "facts": "primary"},
    }), encoding="utf-8")
    monkeypatch.setenv("FUNDLEX_MODEL_ROLES_FILE", str(path))
    monkeypatch.setenv("TEST_PRIMARY_KEY", "pk")
    monkeypatch.setenv("TEST_REVIEW_KEY", "rk")
    configs, overrides = load_role_config()
    assert configs["primary"].api_key == "pk"
    assert configs["review"].api_key == "rk"
    assert configs["review"].max_tokens == 222
    assert overrides == {"compose_review": "review", "facts": "primary"}


def test_build_role_gateway_shares_budget_and_only_builds_two_transports_when_needed(
        monkeypatch: pytest.MonkeyPatch):
    _clear_role_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "a")
    monkeypatch.setenv("LLM_BASE_URL", "https://a.invalid")
    monkeypatch.setenv("LLM_API_KEY", "ka")
    built: list[str] = []

    def factory(cfg, budget):
        built.append(cfg.role)
        return StubGateway(cfg.model)

    gateway = build_role_gateway(gateway_factory=factory)
    assert built == ["primary"]
    assert gateway.review is gateway.primary

    built.clear()
    monkeypatch.setenv("FUNDLEX_REVIEW_MODEL", "b")
    monkeypatch.setenv("FUNDLEX_REVIEW_BASE_URL", "https://b.invalid")
    monkeypatch.setenv("FUNDLEX_REVIEW_API_KEY", "kb")
    gateway = build_role_gateway(gateway_factory=factory)
    assert built == ["primary", "review"]
    assert gateway.review is not gateway.primary


def test_unknown_role_in_task_map_is_rejected():
    with pytest.raises(RoleConfigError):
        RoleGateway(StubGateway("a"), StubGateway("b"),
                    task_roles={"recall_verify": "chief"})
