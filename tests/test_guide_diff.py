"""Deterministic guide-version diff: same inputs always produce same output."""
from __future__ import annotations

import copy
import json

import pytest

from fundlex import guide_store
from fundlex.guide_diff import ALGORITHM, diff_guide_documents


def doc(rules, *, parser="guide-parse-1", source="aa" * 32, clean=True, findings=0) -> dict:
    return {"schema_version": "guide-rules-v1", "parser_version": parser,
            "source_sha256": source,
            "prompt_versions": {"guide_parse": "guide_parse_v1"},
            "groups": rules,
            "validation": {"errors": [], "warnings": [], "coverage_gaps": [], "clean": clean,
                           "rounds": 1,
                           "verification": {"findings": [{"kind": "missing"}] * findings,
                                            "invalid_findings": 0}}}


def rule(rule_id, title="规则", requirement="要求", operations=None, **extra):
    return {"rule_id": rule_id, "title": title, "requirement": requirement,
            "operations": operations or [{"op": "append", "new_text": "新文"}], **extra}


def test_identical_documents_produce_empty_diff():
    base = doc([rule("G01"), rule("G02")])
    result = diff_guide_documents(base, copy.deepcopy(base))
    assert result["algorithm"] == ALGORITHM
    assert result["summary"]["identical"] is True
    assert result["summary"]["rules_before"] == result["summary"]["rules_after"] == 2
    assert result["rules"] == {"added": [], "removed": [], "changed": []}
    assert result["groups"] == {"added": [], "removed": [], "order_changed": False}
    assert result["meta"] == {}


def test_diff_is_deterministic_and_key_order_insensitive():
    before = doc([rule("G01", operations=[{"op": "replace", "old_text": "旧", "new_text": "新"}])])
    # Same content, different key insertion order inside the rule.
    shuffled = {"operations": [{"new_text": "新", "op": "replace", "old_text": "旧"}],
                "requirement": "要求", "rule_id": "G01", "title": "规则"}
    after = doc([shuffled])
    first = diff_guide_documents(before, after)
    second = diff_guide_documents(before, after)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["summary"]["identical"] is True


def test_added_removed_and_field_level_changes():
    before = doc([rule("G01", title="旧标题"), rule("G02")])
    after = doc([rule("G01", title="新标题"), rule("G03", references=["销售费用新规第三条"])])
    result = diff_guide_documents(before, after)
    assert result["summary"]["identical"] is False
    assert [item["rule_id"] for item in result["rules"]["added"]] == ["G03"]
    assert [item["rule_id"] for item in result["rules"]["removed"]] == ["G02"]
    changed = result["rules"]["changed"]
    assert len(changed) == 1 and changed[0]["rule_id"] == "G01"
    assert changed[0]["fields"] == {"title": {"old": "旧标题", "new": "新标题"}}
    # Added rules carry the full rule payload for display.
    assert result["rules"]["added"][0]["rule"]["references"] == ["销售费用新规第三条"]


def test_only_changed_fields_are_recorded():
    before = doc([rule("G01", title="不变", requirement="旧要求",
                       operations=[{"op": "delete", "old_text": "删除"}])])
    after = doc([rule("G01", title="不变", requirement="新要求",
                       operations=[{"op": "delete", "old_text": "删除"}])])
    result = diff_guide_documents(before, after)
    assert result["rules"]["changed"][0]["fields"] == {"requirement": {"old": "旧要求", "new": "新要求"}}


def test_groups_structure_and_order_changes():
    before = doc([rule("G01"), rule("G02")])
    after = doc([rule("G02"), rule("G01"), rule("G03")])
    result = diff_guide_documents(before, after)
    assert result["groups"]["added"] == ["G03"]
    assert result["groups"]["removed"] == []
    assert result["groups"]["order_changed"] is True
    assert result["summary"]["groups_order_changed"] is True


def test_nested_groups_are_flattened_and_compared():
    before = {"groups": [{"group_id": "grp-a", "rules": [rule("G01"), rule("G02")]}]}
    after = {"groups": [{"group_id": "grp-a", "rules": [rule("G01"), rule("G02", title="改名")]}]}
    result = diff_guide_documents(before, after)
    assert [change["rule_id"] for change in result["rules"]["changed"]] == ["G02"]
    assert result["groups"]["added"] == result["groups"]["removed"] == []


def test_meta_and_validation_summary_diff():
    before = doc([rule("G01")], parser="guide-parse-1", clean=True)
    after = doc([rule("G01")], parser="guide-parse-2", source="bb" * 32, clean=False, findings=2)
    result = diff_guide_documents(before, after)
    assert result["meta"]["parser_version"] == {"old": "guide-parse-1", "new": "guide-parse-2"}
    assert result["meta"]["source_sha256"] == {"old": "aa" * 32, "new": "bb" * 32}
    assert result["validation"]["before"] == {"clean": True, "errors": 0, "warnings": 0,
                                              "coverage_gaps": 0, "findings": 0,
                                              "invalid_findings": 0, "rounds": 1}
    assert result["validation"]["after"]["clean"] is False
    assert result["validation"]["after"]["findings"] == 2


def test_store_diff_versions_owner_isolation_and_unparsed(tmp_path):
    from docx import Document
    import io

    from fundlex.store import RunStore

    def docx_bytes() -> bytes:
        stream = io.BytesIO()
        document = Document()
        document.add_paragraph("指引")
        document.save(stream)
        return stream.getvalue()

    store = RunStore(tmp_path / "state")
    guide_store.ensure_builtin_guide(store)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", docx_bytes())
    a_job = guide_store.claim_guide_job(store)
    first = guide_store.finish_guide_job(store, a_job["id"], a_job["fencing_token"],
                                         document=doc([rule("G01")]))["version"]
    reparsed = guide_store.reparse_version(store, "alice", first["id"])
    b_job = guide_store.claim_guide_job(store)
    second = guide_store.finish_guide_job(store, b_job["id"], b_job["fencing_token"],
                                          document=doc([rule("G01", title="改"), rule("G02")]))["version"]
    assert reparsed["id"] == second["id"]
    result = guide_store.diff_versions(store, "alice", second["id"], first["id"])
    assert [item["rule_id"] for item in result["rules"]["added"]] == ["G02"]
    assert result["rules"]["changed"][0]["rule_id"] == "G01"
    # The built-in version participates in diffs for any owner.
    builtin_cmp = guide_store.diff_versions(store, "alice", second["id"], guide_store.BUILTIN_GUIDE_ID)
    assert builtin_cmp["summary"]["rules_before"] == len(
        guide_store.guide_document(store, guide_store.BUILTIN_GUIDE_ID)["groups"])
    # Another owner cannot see or diff Alice's custom versions.
    with pytest.raises(KeyError):
        guide_store.diff_versions(store, "bob", second["id"], first["id"])
    # Unparsed versions have no document to diff.
    staged = guide_store.create_custom_version(store, "alice", "again.docx", docx_bytes())
    with pytest.raises(KeyError):
        guide_store.diff_versions(store, "alice", first["id"], staged["id"])
    with pytest.raises(ValueError, match="GUIDE_DIFF_AGAINST_REQUIRED"):
        guide_store.diff_versions(store, "alice", first["id"], "  ")
