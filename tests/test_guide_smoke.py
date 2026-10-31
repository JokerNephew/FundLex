"""Footprint smoke: deterministic needs_review marking against the lineage baseline."""
from __future__ import annotations

import io

import pytest
from docx import Document

from fundlex import guide_store
from fundlex.guide import GUIDE_SCHEMA_VERSION
from fundlex.guide_smoke import review_version_footprint
from fundlex.store import RunStore


def docx_bytes(label: str) -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(label)
    document.save(stream)
    return stream.getvalue()


def document(rules, *, paragraphs=None) -> dict:
    groups = []
    for pos, rid in enumerate(rules):
        span = paragraphs[rid] if paragraphs and rid in paragraphs else [pos]
        groups.append({"rule_id": rid, "title": f"规则{rid}", "source_paragraphs": span})
    return {"schema_version": GUIDE_SCHEMA_VERSION, "parser_version": "guide-parse-1",
            "groups": groups,
            "validation": {"errors": [], "warnings": [], "coverage_gaps": [], "clean": True,
                           "verification": {"findings": [], "invalid_findings": 0}}}


def make_store(tmp_path) -> RunStore:
    store = RunStore(tmp_path / "state")
    guide_store.ensure_builtin_guide(store)
    return store


def parse(store, owner="alice", label="自定义指引", data=None, rules=("G01",)) -> dict:
    version = guide_store.create_custom_version(store, owner, f"{label}.docx",
                                                data or docx_bytes(label))
    job = guide_store.claim_guide_job(store)
    return guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                        document=document(list(rules)))["version"]


def test_same_source_as_builtin_degraded_marked_needs_review(tmp_path):
    store = make_store(tmp_path)
    builtin_source = guide_store.BUILTIN_GUIDE_PATH
    # The built-in source DOCX is not stored; emulate by patching the version's
    # source hash to equal the built-in document's source hash.
    import json
    builtin_doc = json.loads(builtin_source.read_text(encoding="utf-8"))
    parsed = parse(store, rules=("G01", "G02"))
    with store._connect() as db:
        db.execute("UPDATE guide_versions SET source_sha256=? WHERE id=?",
                   (builtin_doc["source_sha256"], parsed["id"]))
    result = review_version_footprint(store, "alice", parsed["id"])
    assert result["needs_review"] is True
    dims = result["dimensions"]
    assert dims["baseline_version_id"] == guide_store.BUILTIN_GUIDE_ID
    assert dims["rules_before"] == len(builtin_doc["groups"]) and dims["rules_after"] == 2
    assert len(dims["removed_rule_ids"]) == len(builtin_doc["groups"]) - 2
    assert dims["granularity_only"] is False
    assert dims["coverage_lost_paragraphs"]
    version = guide_store.get_version(store, "alice", parsed["id"])
    assert version["review"]["status"] == "needs_review"
    assert version["review"]["dimensions"] == dims
    # Advisory only — the version can still be enabled.
    guide_store.set_current_guide(store, "alice", parsed["id"])


def test_reparse_lineage_regression_and_recovery(tmp_path):
    store = make_store(tmp_path)
    first = parse(store, rules=("G01", "G02", "G03"))
    reparsed = guide_store.reparse_version(store, "alice", first["id"])
    job = guide_store.claim_guide_job(store)
    second = guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                          document=document(["G01", "G03"]))["version"]
    assert second["id"] == reparsed["id"]
    degraded = review_version_footprint(store, "alice", second["id"])
    assert degraded["needs_review"] is True
    assert degraded["dimensions"]["baseline_version_id"] == first["id"]
    assert degraded["dimensions"]["removed_rule_ids"] == ["G02"]
    assert degraded["dimensions"]["cliff"] is False

    third_req = guide_store.reparse_version(store, "alice", second["id"])
    job = guide_store.claim_guide_job(store)
    third = guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                         document=document(["G01", "G02", "G03"],
                                                           paragraphs={"G01": [0], "G02": [1], "G03": [2]}))
    healthy = review_version_footprint(store, "alice", third["version"]["id"])
    assert healthy["needs_review"] is False
    assert healthy["baseline"] == third_req["parent_version_id"]
    cleared = guide_store.get_version(store, "alice", third["version"]["id"])
    assert cleared["review"] is None
    # Changed-but-complete footprints stay quiet.
    quiet = review_version_footprint(store, "alice", first["id"])
    assert quiet["skipped"] == "no_baseline"


def test_rule_id_churn_without_coverage_loss_is_granularity_only(tmp_path):
    """Merged/split rules keep every source paragraph: advisory must say so."""
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "base.docx", docx_bytes("基线"))
    job = guide_store.claim_guide_job(store)
    first = guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                         document=document(["G01", "G02"],
                                                           paragraphs={"G01": [0, 1], "G02": [2]}))["version"]
    reparsed = guide_store.reparse_version(store, "alice", first["id"])
    job = guide_store.claim_guide_job(store)
    merged = guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                          document=document(["G01"],
                                                            paragraphs={"G01": [0, 1, 2]}))["version"]
    result = review_version_footprint(store, "alice", merged["id"])
    assert result["needs_review"] is True
    assert result["dimensions"]["removed_rule_ids"] == ["G02"]
    assert result["dimensions"]["granularity_only"] is True
    assert result["dimensions"]["coverage_lost_paragraphs"] == []


def test_unrelated_new_guide_has_no_baseline(tmp_path):
    store = make_store(tmp_path)
    version = parse(store, rules=("X01",))
    result = review_version_footprint(store, "alice", version["id"])
    assert result == {"baseline": None, "needs_review": False, "dimensions": {},
                      "skipped": "no_baseline"}
    assert guide_store.get_version(store, "alice", version["id"])["review"] is None


def test_failed_or_unparsed_versions_are_skipped(tmp_path):
    store = make_store(tmp_path)
    staged = guide_store.create_custom_version(store, "alice", "pending.docx", docx_bytes("x"))
    result = review_version_footprint(store, "alice", staged["id"])
    assert result["skipped"] == "uploaded"
    with pytest.raises(KeyError):
        review_version_footprint(store, "bob", staged["id"])


def test_worker_parse_stamps_needs_review_after_certified_finish(tmp_path, monkeypatch):
    """The worker path reports parse -> gate -> footprint smoke in one run."""
    from fundlex.jobs import Worker

    store = make_store(tmp_path)
    import json as _json
    builtin_doc = _json.loads(guide_store.BUILTIN_GUIDE_PATH.read_text(encoding="utf-8"))
    version = guide_store.create_custom_version(store, "alice", "same-source.docx",
                                                docx_bytes("同源指引"))
    with store._connect() as db:
        db.execute("UPDATE guide_versions SET source_sha256=? WHERE id=?",
                   (builtin_doc["source_sha256"], version["id"]))
    worker = Worker(store)
    # The model work is replaced by the channel's stage contract: a clean
    # document still gets footprint-reviewed after the certified finish.
    monkeypatch.setattr("fundlex.guide.build_guide_document",
                        lambda source, gateway, **kw: document(["G01"]))
    monkeypatch.setattr("fundlex.guide.extract_guide_source", lambda path: None)
    monkeypatch.setattr("fundlex.model.ModelGateway.from_env",
                        staticmethod(lambda: None), raising=False)
    assert worker._run_guide_job() is True
    finished = guide_store.get_version(store, "alice", version["id"])
    assert finished["status"] == "parsed"
    assert finished["review"]["status"] == "needs_review"
    assert len(finished["review"]["dimensions"]["removed_rule_ids"]) == len(builtin_doc["groups"]) - 1
