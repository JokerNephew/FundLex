"""Real ModelGateway/GuideModelRouter protocol checks with transport stubs only."""
import json

import httpx
import jsonschema
import pytest

from fundlex.guide_generation import prompts
from fundlex.guide_generation.model_router import GuideModelRouter, TASK_DEFAULT_ROLE
from fundlex.model import (GUIDE_GENERATION_TASK_TYPES, ModelError, ModelGateway,
                           QUOTE_SELF_VALIDATED_TASKS, TASK_TYPES)
from fundlex.model_budget import ModelBudget


PROMPT_PREFIXES = {
    "guide_req_extract": "REQUIREMENT_EXTRACT", "guide_req_review": "REQUIREMENT_REVIEW",
    "guide_intent": "INTENT", "guide_impact_sweep": "IMPACT_SWEEP",
    "guide_impact_adjudicate": "IMPACT_ADJUDICATE", "guide_local_candidate": "LOCAL_CANDIDATE",
    "guide_merge": "MERGE", "guide_quality_review": "QUALITY", "guide_coverage_audit": "COVERAGE",
    "guide_residual_sweep": "RESIDUAL", "guide_applicability": "APPLICABILITY",
    "guide_engine_map": "ENGINE", "guide_repair": "REPAIR",
}


def minimum_value(schema):
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        return {key: minimum_value(schema["properties"][key]) for key in schema.get("required", [])}
    if kind == "array":
        return [minimum_value(schema["items"]) for _ in range(schema.get("minItems", 0))]
    if kind == "string":
        return "源" * max(1, schema.get("minLength", 0))
    if kind == "boolean":
        return False
    if kind in {"integer", "number"}:
        return schema.get("minimum", 0)
    raise AssertionError(f"unsupported fixture schema type: {kind}")


def test_generation_task_registry_exactly_matches_router():
    assert set(PROMPT_PREFIXES) == set(TASK_DEFAULT_ROLE) == GUIDE_GENERATION_TASK_TYPES
    assert GUIDE_GENERATION_TASK_TYPES <= TASK_TYPES
    assert GUIDE_GENERATION_TASK_TYPES <= QUOTE_SELF_VALIDATED_TASKS


@pytest.mark.parametrize("task_type", sorted(PROMPT_PREFIXES))
def test_all_generation_tasks_through_actual_gateway_and_router(tmp_path, task_type):
    prefix = PROMPT_PREFIXES[task_type]
    schema = getattr(prompts, prefix + "_SCHEMA")
    instruction = getattr(prompts, prefix + "_INSTRUCTION")
    version = getattr(prompts, prefix + "_VERSION")
    value = minimum_value(schema)
    jsonschema.validate(value, schema)
    seen = []

    def transport(request):
        assert str(request.url) == "https://model.invalid/v1/chat/completions"
        payload = json.loads(request.content)
        seen.append(payload)
        system = payload["messages"][0]["content"]
        assert "regulation is the only source of new legal requirements" in system
        assert "Draft contract wording only when the schema explicitly asks for it" in system
        assert instruction in system
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"model": "stub-actual", "choices": [{
            "message": {"content": json.dumps(value)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})

    budget = ModelBudget(tmp_path / "stub-only-ledger.sqlite", max_requests=2, max_cost_usd=1)
    gateway = ModelGateway(base_url="https://model.invalid/v1", model="stub", api_key="stub-only",
                           client=httpx.Client(transport=httpx.MockTransport(transport)),
                           budget=budget, retries=0, mode="live")
    router = GuideModelRouter({"primary": gateway})
    try:
        result = router.call(task_type=task_type, bounded_context="[REGULATION] 测试原文",
                             response_schema=schema, instruction=instruction, prompt_version=version)
        assert result.value == value
        assert result.task_type == task_type
        assert result.attempts == 1
        assert len(seen) == 1
        assert router.records[0].role == TASK_DEFAULT_ROLE[task_type]
        assert router.records[0].error_code == ""
        assert budget.snapshot()["statuses"] == {"completed": 1}
    finally:
        gateway.close()


@pytest.mark.parametrize("task_type", sorted(PROMPT_PREFIXES))
def test_generation_gateway_still_rejects_invalid_response_schema(task_type):
    schema = getattr(prompts, PROMPT_PREFIXES[task_type] + "_SCHEMA")
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "model": "stub", "choices": [{"message": {"content": "[]"}, "finish_reason": "stop"}]})))
    with ModelGateway(base_url="https://model.invalid", model="stub", api_key="stub-only",
                       client=client, retries=0, mode="live") as gateway:
        with pytest.raises(ModelError, match="MODEL_SCHEMA_INVALID"):
            gateway.call(task_type=task_type, bounded_context="法规原文", response_schema=schema,
                         instruction="test schema contract")


def test_existing_guide_parse_and_revision_prompt_behavior_is_unchanged():
    with ModelGateway(base_url="https://model.invalid", model="stub", api_key="stub-only",
                       client=httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("no HTTP expected")))) as gateway:
        parse = gateway._system_prompt("guide_parse", "old parse", {"type": "object"})
        compose = gateway._system_prompt("recall_compose", "old compose", {"type": "object"})
        assert "copied verbatim from the guide source" in parse
        assert "Fixed policy text" in compose
        assert "regulation is the only source" not in parse + compose
