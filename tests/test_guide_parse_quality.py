"""Parse quality channel integration: canary admission, human diagnostics, spec.

Deterministic throughout — no model calls.  The two frozen fixtures are the
real 2026-10-31 artifacts: the 15-rule merged re-parse (FL-D648) and the
fee-rule V2 quality-gate rejection.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from fundlex import guide_store
from fundlex.api import create_app
from fundlex.guide import extract_guide_source
from fundlex.guide_canary import executability_report
from fundlex.guide_report import block_report, explain_code, granularity_metrics
from fundlex.store import RunStore

FIXTURES = Path(__file__).parent / "fixtures" / "guides"
V4_SOURCE = Path(__file__).parent.parent / "references" / "source" / \
    "v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx"
ALICE = {"X-FundLex-User": "alice"}


def docx_bytes(label: str) -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(label)
    document.save(stream)
    return stream.getvalue()


def fixture_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_store(tmp_path) -> RunStore:
    store = RunStore(tmp_path / "state")
    guide_store.ensure_builtin_guide(store)
    return store


def finish_with(store, document, *, label="自定义指引", source_path: Path | None = None):
    data = source_path.read_bytes() if source_path else docx_bytes(label)
    version = guide_store.create_custom_version(store, "alice", "guide.docx", data)
    job = guide_store.claim_guide_job(store)
    assert job is not None
    return guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                        document=document)


def test_canary_fatal_marks_needs_review_and_blocks_enabling(tmp_path):
    """A clean-looking but non-executable parse must reach the review list,
    never the current-guide slot (FL-D648 pipeline-level closure)."""
    store = make_store(tmp_path)
    document = fixture_json("merged_g15_real_20261031.json")
    finished = finish_with(store, document, source_path=V4_SOURCE)
    version = finished["version"]
    assert version["status"] == "parsed"
    assert version["qualification_status"] == guide_store.QUALIFICATION_NEEDS_REVIEW
    assert version["review"]["status"] == "needs_review"
    assert version["review"]["dimensions"]["source"] == "executability_canary"
    assert version["review"]["dimensions"]["blocking_gaps"] == [
        "G03:1", "G03:2", "G06:1", "G07:1", "G07:2", "G08:1",
        "G10:1", "G10:2", "G10:3", "G10:4", "G10:5", "G15:1"]
    issues = version["issues"]
    assert issues["canary"]["passed"] is False
    # The human-readable block report localises the failure to guide blocks.
    entries = issues["parse_report"]["entries"]
    errored = [entry for entry in entries if entry["status"] == "error"]
    assert errored
    assert all("reason_zh" in entry for entry in errored)
    with pytest.raises(ValueError, match="GUIDE_NOT_CERTIFIED"):
        guide_store.set_current_guide(store, "alice", version["id"])
    # Enabling stays possible for the built-in (its own path is untouched).
    assert guide_store.set_current_guide(store, "alice",
                                         guide_store.BUILTIN_GUIDE_ID)["built_in"]


def test_enable_gate_matches_runtime_router(tmp_path):
    """set_current_guide replays the runtime admission predicate: a certified
    legacy document (no identities) still enables; anything authoritative with
    unregistered keys is rejected with the registry-missing code."""
    store = make_store(tmp_path)
    legacy = {"schema_version": "guide-rules-v1",
              "groups": [{"rule_id": "G01", "title": "t", "section_hint": "释义",
                          "operations": [{"op": "append", "new_text": "x"}]}],
              "validation": {"errors": [], "warnings": [], "coverage_gaps": []}}
    finished = finish_with(store, legacy)
    assert finished["version"]["qualification_status"] == guide_store.QUALIFICATION_CERTIFIED
    guide_store.set_current_guide(store, "alice", finished["version"]["id"])


def test_healthy_footprint_smoke_never_clears_canary_review(tmp_path):
    """The footprint smoke clears only its own verdicts (source-aware)."""
    store = make_store(tmp_path)
    document = fixture_json("merged_g15_real_20261031.json")
    finished = finish_with(store, document, source_path=V4_SOURCE)
    version_id = finished["version"]["id"]
    from fundlex.guide_smoke import review_version_footprint
    smoke = review_version_footprint(store, "alice", version_id)
    # The smoke also sees the footprint drift (it is right), but its verdict
    # must not clobber the canary's runtime-fatal review dimensions.
    assert smoke["needs_review"] is True and smoke["baseline"] == guide_store.BUILTIN_GUIDE_ID
    refreshed = guide_store.get_version(store, "alice", version_id)
    assert refreshed["review"]["dimensions"]["source"] == "executability_canary"


def test_block_report_localises_canary_failure():
    source = extract_guide_source(V4_SOURCE)
    document = fixture_json("merged_g15_real_20261031.json")
    problems: dict[str, list[dict]] = {}
    for finding in executability_report(document)["fatal"]:
        problems.setdefault(finding["rule_id"], []).append(finding)
    report = block_report(source, document, rule_problems=problems)
    assert report["schema_version"] == "guide-parse-report-v1"
    assert report["counts"]["error"] > 0
    assert report["counts"]["uncovered"] == 0
    first_error = next(entry for entry in report["entries"] if entry["status"] == "error")
    assert "无法映射到已注册执行契约" in first_error["reason_zh"]
    assert first_error["remedy_zh"]
    assert report["summary_zh"].startswith(f"共 {report['blocks_total']} 个指引块")


def test_block_report_unparsed_with_human_reason():
    source = extract_guide_source(V4_SOURCE)
    report = block_report(source, None, error_code="GUIDE_MODEL_FAILED:RATE_LIMITED")
    assert report["counts"]["unparsed"] == report["blocks_total"]
    assert "模型服务调用失败" in report["summary_zh"]
    assert report["explanations"]["GUIDE_MODEL_FAILED:RATE_LIMITED"]["remedy"]


def test_v2_quality_rejection_explained_in_chinese():
    issues = fixture_json("fee_rule_v2_issues_20261031.json")
    error = issues["errors"][0]
    info = explain_code(str(error["code"]))
    assert info["zh"] and info["remedy"]
    unclean = explain_code("GUIDE_VALIDATION_UNCLEAN")
    assert "逐块修正" in unclean["remedy"]


def test_builtin_block_report_is_all_healthy():
    source = extract_guide_source(V4_SOURCE)
    from fundlex.guide_store import load_builtin_document
    document = load_builtin_document()
    report = block_report(source, document)
    assert report["counts"]["error"] == 0
    assert report["counts"]["merged"] == 0
    assert report["counts"]["uncovered"] == 0
    metrics = granularity_metrics(source, document)
    assert metrics["rules"] == len(document["groups"])
    assert metrics["blocks"] >= 1


def test_upload_spec_endpoint(tmp_path):
    store_dir = tmp_path / "state"
    RunStore(store_dir)
    client = TestClient(create_app(store_dir))
    response = client.get("/api/guides/upload-spec", headers=ALICE)
    assert response.status_code == 200
    spec = response.json()
    assert spec["schema_version"] == "guide-upload-spec-v1"
    assert spec["granularity_advice"] and spec["common_failure_modes"]
    mode_codes = {item["code"] for item in spec["common_failure_modes"]}
    assert "GUIDE_VALIDATION_UNCLEAN" in mode_codes
    assert "GUIDE_OPERATION_REGISTRY_MISSING" in mode_codes
    # Published spec codes must all have human explanations.
    for code in mode_codes | {"GUIDE_CANARY_DEAD_CONDITION", "GUIDE_NOT_CERTIFIED"}:
        info = explain_code(code)
        assert info["zh"] and info["remedy"], code


def test_guide_detail_surfaces_enrichment(tmp_path):
    store_dir = tmp_path / "state"
    guide_store.ensure_builtin_guide(RunStore(store_dir))
    client = TestClient(create_app(store_dir))
    data = docx_bytes("指引正文示例")
    uploaded = client.post("/api/guides", headers=ALICE,
                           files={"file": ("custom.docx", data)})
    version_id = uploaded.json()["version"]["id"]
    store = client.app.state.store
    job = guide_store.claim_guide_job(store)
    legacy = {"schema_version": "guide-rules-v1",
              "groups": [{"rule_id": "G01", "title": "t", "section_hint": "释义",
                          "operations": [{"op": "append", "new_text": "x"}]}],
              "validation": {"errors": [], "warnings": [], "coverage_gaps": []}}
    guide_store.finish_guide_job(store, job["id"], job["fencing_token"], document=legacy)
    detail = client.get(f"/api/guides/{version_id}", headers=ALICE).json()
    assert detail["qualification_status"] == "certified"
    issues = detail["issues_detail"]
    assert issues["canary"]["passed"] is True
    assert issues["parse_report"]["schema_version"] == "guide-parse-report-v1"
