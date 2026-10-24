"""Unclassified pipeline failures retain metering through Worker persistence (FL-D200)."""
import json

import pytest

from fundlex.jobs import Worker
from fundlex.recall_pipeline import process_recall_first
from fundlex.store import RunStore
from test_recall_pipeline import PipelineGateway, base_responses, build_contract, guide_document


@pytest.mark.parametrize("error", [NameError, RuntimeError])
def test_worker_keeps_failed_pipeline_metrics_and_sanitizes_exception(tmp_path, monkeypatch, error):
    import fundlex.recall_pipeline as pipeline

    source = tmp_path / "source.docx"
    build_contract(source)
    store = RunStore(tmp_path / "data")
    batch = store.create_batch(owner="alice", ruleset_version="v1",
                               uploads=[("source.docx", source.read_bytes())])
    model = PipelineGateway(base_responses())
    expected_metrics = {**model.metrics(), "logical_calls": 3, "http_attempts": 4,
                        "estimated_cost_usd": 0.00125, "prompt_tokens": 700,
                        "completion_tokens": 120, "total_tokens": 820}
    monkeypatch.setattr(model, "metrics", lambda: expected_metrics)

    def broken_scope(*args, **kwargs):
        assert model.calls  # the failure occurs after model work, not before it
        raise error("private-exception-content-not-for-report")

    monkeypatch.setattr(pipeline, "scope_map", broken_scope)
    worker = Worker(store, lambda src, out, version: process_recall_first(
        src, out, guide_document=guide_document(), gateway=model))
    assert worker.run_once()
    row = store.get_batch("alice", batch["id"])["documents"][0]
    assert row["status"] == "failed"
    assert row["error_code"] == "PROCESSING_FAILED"
    assert row["delivery_status"] == "not_generated"
    # Read the actual persisted Worker report, not only the returned dictionary.
    report_path, _ = store.get_artifact("alice", batch["id"], row["id"], "report_json")
    report = json.loads(report_path.read_text())
    for key, value in expected_metrics.items():
        assert report["model"][key] == value
    assert report["errors"][-1]["message"] == error.__name__
    assert "private-exception-content" not in report_path.read_text()
    assert report["duration_ms"] >= 0
    assert report["artifacts"] == {}
