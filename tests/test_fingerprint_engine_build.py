"""Production build and checkpoint namespace fingerprints."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from fundlex import checkpoints, store


def _write(root: Path, relative: str, content: str = "v1") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_engine_build_covers_generation_rules_and_guides_but_excludes_ui_and_evidence(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "workspace"
    _write(root, "fundlex/generation/router.py")
    _write(root, "fundlex/recall.py")
    _write(root, "rules/compile.py")
    _write(root, "rules/rules.json")
    _write(root, "guides/builtin.json")
    _write(root, "frontend/app.js")
    _write(root, "docs/evidence/run.json")
    monkeypatch.setattr(store, "_ENGINE_BUILD_ROOT", root)

    baseline = store.engine_build()
    for relative in (
            "fundlex/generation/router.py",
            "fundlex/recall.py",
            "rules/compile.py",
            "rules/rules.json",
            "guides/builtin.json"):
        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")
        assert store.engine_build() != baseline, relative
        baseline = store.engine_build()

    unchanged = store.engine_build()
    _write(root, "frontend/app.js", "ui changed")
    _write(root, "docs/evidence/run.json", json.dumps({"changed": True}))
    assert store.engine_build() == unchanged


def test_engine_build_ignores_operational_modules_while_service_build_covers_them(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "workspace"
    _write(root, "fundlex/recall_pipeline.py")
    _write(root, "fundlex/generation/router.py")
    _write(root, "fundlex/api.py")
    _write(root, "fundlex/auth.py")
    _write(root, "fundlex/tasks.py")
    _write(root, "fundlex/application/task_service.py")
    _write(root, "fundlex/integrations/feishu/service.py")
    _write(root, "fundlex/compare/service.py")
    _write(root, "rules/rules_v1.json")
    _write(root, "guides/builtin_guide_v1.json")
    monkeypatch.setattr(store, "_ENGINE_BUILD_ROOT", root)

    engine = store.engine_build()
    service = store.service_build()
    for relative in (
            "fundlex/api.py",
            "fundlex/auth.py",
            "fundlex/tasks.py",
            "fundlex/application/task_service.py",
            "fundlex/integrations/feishu/service.py",
            "fundlex/compare/service.py"):
        _write(root, relative, f"operational change: {relative}")
        assert store.engine_build() == engine, relative
        assert store.service_build() != service, relative
        service = store.service_build()

    _write(root, "fundlex/recall_pipeline.py", "core change")
    assert store.engine_build() != engine
    assert store.service_build() != service


def test_engine_build_manifest_is_a_subset_of_service_sources():
    root = store._ENGINE_BUILD_ROOT
    engine = {path.relative_to(root).as_posix() for path in store._engine_build_files()}
    service = {path.relative_to(root).as_posix() for path in store._service_build_files()}

    assert engine <= service
    for relative in (
            "fundlex/recall_pipeline.py",
            "fundlex/recall.py",
            "fundlex/recall_prompts.py",
            "fundlex/rules.py",
            "fundlex/rules_v2.py",
            "fundlex/rule_scope.py",
            "fundlex/docx.py",
            "fundlex/model.py",
            "fundlex/model_budget.py",
            "fundlex/pipeline.py",
            "fundlex/v2_pipeline.py",
            "fundlex/v2.py",
            "fundlex/delivery.py",
            "fundlex/obligations.py",
            "fundlex/applicability.py",
            "fundlex/targeting.py",
            "fundlex/selective.py",
            "fundlex/edit_summary.py",
            "fundlex/checkpoints.py",
            "fundlex/stage_replay.py",
            "fundlex/frozen.py",
            "fundlex/generation/router.py",
            "fundlex/models/roles.py",
            "fundlex/recovery/policies.py",
            "rules/rules_v1.json",
            "guides/builtin_guide_v1.json"):
        assert relative in engine, relative

    for relative in (
            "fundlex/api.py",
            "fundlex/auth.py",
            "fundlex/db.py",
            "fundlex/html_view.py",
            "fundlex/observability.py",
            "fundlex/tasks.py",
            "fundlex/guide_store.py",
            "fundlex/api_errors.py",
            "fundlex/config.py",
            "fundlex/upload_guard.py",
            "fundlex/upload_validation.py",
            "fundlex/jobs.py",
            "fundlex/application/task_service.py",
            "fundlex/integrations/feishu/service.py",
            "fundlex/compare/service.py"):
        assert relative not in engine, relative
        assert relative in service, relative


@pytest.mark.parametrize("relative", store._ENGINE_BUILD_MODULES)
def test_engine_build_allowlist_entries_exist(relative: str):
    # A typo or rename in the explicit allowlist must fail loudly instead of
    # silently dropping a result-affecting module from the fingerprint.
    assert (store._ENGINE_BUILD_ROOT / relative).is_file(), relative


def test_engine_build_is_stable_for_manifest_order(tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "workspace"
    _write(root, "fundlex/docx.py")
    _write(root, "fundlex/recall.py")
    _write(root, "rules/z.json")
    _write(root, "guides/a.json")
    monkeypatch.setattr(store, "_ENGINE_BUILD_ROOT", root)

    first = store.engine_build()
    assert store._engine_build_files() == tuple(sorted(
        store._engine_build_files(),
        key=lambda path: path.relative_to(root).as_posix()))
    assert store.engine_build() == first


def test_checkpoint_dependencies_bind_current_engine_build(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store, "engine_build", lambda: "a" * 64)
    first = checkpoints.ModelCheckpoints(tmp_path / "checkpoints", {
        "source": "source-1", "engine_build": "stale-caller-value"})
    assert first.dependencies["engine_build"] == "a" * 64

    monkeypatch.setattr(store, "engine_build", lambda: "b" * 64)
    second = checkpoints.ModelCheckpoints(tmp_path / "checkpoints", {"source": "source-1"})
    assert second.dependencies["engine_build"] == "b" * 64
    assert first.dependencies != second.dependencies


def test_checkpoint_requires_actual_context_and_successful_original_response(tmp_path: Path,
                                                                              monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store, "engine_build", lambda: "a" * 64)
    checkpoints_store = checkpoints.ModelCheckpoints(tmp_path / "checkpoints", {"source": "source-1"})
    context = "合同原文片段"
    query = {"task_type": "facts", "prompt_version": "v1",
             "bounded_context_sha256": hashlib.sha256(context.encode()).hexdigest()}
    schema = {"type": "object", "required": ["quote"],
              "properties": {"quote": {"type": "string"}}}
    event = {"task_type": "facts", "prompt_version": "v1",
             "context_sha256": query["bounded_context_sha256"],
             "actual_model": "test-model", "http_status": 200}
    checkpoints_store.save(query, {"quote": "原文"}, event)
    assert checkpoints_store.load(query, context, schema)[0] == {"quote": "原文"}

    wrong_context = "另一段原文"
    assert checkpoints_store.load(query, wrong_context, schema) is None
    with pytest.raises(ValueError, match="only successful bound responses"):
        checkpoints_store.save(query, {"quote": "原文"}, {**event, "reused_checkpoint": True})


def test_checkpoint_envelope_and_body_schema_are_bound(tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store, "engine_build", lambda: "a" * 64)
    checkpoints_store = checkpoints.ModelCheckpoints(tmp_path / "checkpoints", {})
    context = "合同原文片段"
    query = {"task_type": "facts", "prompt_version": "v1",
             "bounded_context_sha256": hashlib.sha256(context.encode()).hexdigest()}
    event = {"task_type": "facts", "prompt_version": "v1",
             "context_sha256": query["bounded_context_sha256"],
             "actual_model": "test-model", "http_status": 200}
    checkpoints_store.save(query, {"quote": "原文"}, event)
    path = next((tmp_path / "checkpoints").glob("*.json"))
    record = json.loads(path.read_text(encoding="utf-8"))
    record["body"]["schema"] = "old-checkpoint"
    record["sha256"] = checkpoints.ModelCheckpoints.digest(record["body"])
    path.write_text(json.dumps(record), encoding="utf-8")
    assert checkpoints_store.load(query, context, {"type": "object"}) is None
