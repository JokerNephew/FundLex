"""Frozen stage replay uses real planning/writing/proof with recorded model seams."""
import hashlib
import json

import pytest

from fundlex.frozen import FrozenError, FrozenRun, ModelCassette
from fundlex.recall_pipeline import process_recall_first
from fundlex.stage_replay import STAGES, replay_stage
from test_recall_core import build_contract
from test_recall_pipeline import PipelineGateway, base_responses, guide_document


def test_frozen_pipeline_stages_recompute_without_network(tmp_path, monkeypatch):
    run_dir = tmp_path / "frozen"
    monkeypatch.setenv("FUNDLEX_MODEL_MODE", "record")
    monkeypatch.setenv("FUNDLEX_FROZEN_RUN_DIR", str(run_dir))

    class RecordingGateway(PipelineGateway):
        model = "offline-scripted"

        def call(self, **kwargs):
            result = super().call(**kwargs)
            request = {"task_type": kwargs["task_type"],
                "prompt_version": kwargs.get("prompt_version", "v1"),
                "configured_model": self.model,
                "context_sha256": hashlib.sha256(kwargs["bounded_context"].encode()).hexdigest(),
                "request": {key: kwargs[key] for key in (
                    "bounded_context", "instruction", "response_schema")}}
            ModelCassette(run_dir / "model_calls").save(request, result.value,
                                                       {"actual_model": self.model})
            return result

    source = tmp_path / "contract.docx"
    build_contract(source)
    report = process_recall_first(source, tmp_path / "out", guide_document=guide_document(),
                                  gateway=RecordingGateway(base_responses()))
    assert report["delivery_status"] == "complete", report["unresolved"]
    FrozenRun(run_dir).verify()
    assert {path.name for path in run_dir.glob("*.json")} >= {
        "guide.json", "facts.json", "applicability.json", "scope.json", "targets.json",
        "obligations.json", "plan.json", "edits.json", "claim_replay.json", "audit.json",
        "sweep.json", "report.json", "manifest.json"}
    assert json.loads((run_dir / "claim_replay.json").read_text())["verified"] is True

    def forbidden(*args, **kwargs):
        raise AssertionError("offline stage attempted network or live model setup")
    import httpx
    from fundlex.model import ModelGateway
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(ModelGateway, "from_env", forbidden)
    results = {stage: replay_stage(run_dir, stage) for stage in STAGES}
    assert all(result["model_calls"] == 0 for result in results.values())
    assert results["facts"]["value"]["set_complete_verified"] is True
    assert results["plan"]["value"]["edits"] == report["plan"]["edits"]
    assert results["claim_replay"]["value"]["verified"] is True
    assert results["obligations"]["value"]["counts"] == report["obligations"]["counts"]
    with pytest.raises(FrozenError, match="FROZEN_STAGE_INPUT_MISSING"):
        replay_stage(run_dir, "plan", revision=99)
    # Model cassettes and boundary files are part of the integrity manifest too.
    cassette = next((run_dir / "model_calls").rglob("*.json"))
    cassette.write_text(cassette.read_text() + " ")
    with pytest.raises(FrozenError, match="FROZEN_INTEGRITY_MISMATCH"):
        replay_stage(run_dir, "plan")


def test_stage_replay_missing_manifest_fails_closed(tmp_path):
    with pytest.raises((FrozenError, FileNotFoundError)):
        replay_stage(tmp_path, "plan")
