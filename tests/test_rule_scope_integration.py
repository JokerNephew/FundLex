"""Pipeline integration of :mod:`fundlex.rule_scope` (no model calls).

These pin the three boundaries the pipeline owns: the plan/audit target gate, the
sweep window assignment, and the delete-residual paragraph scan.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fundlex.recall import Target, ensure_delete_targets
from fundlex.recall_pipeline import _apply_scope_gate, _window_rule_scope, _Chunk
from fundlex.rule_scope import RuleScope


def _scope(rule_id: str, locations: tuple[str, ...]) -> RuleScope:
    return RuleScope(
        rule_id=rule_id,
        leaf_ids=frozenset({f"{rule_id}:L01"}) if locations else frozenset(),
        locations=frozenset(locations),
        zone="body" if locations else "",
        include_summary_copies=False,
        copy_keys=frozenset(),
        resolution="resolved" if locations else "unresolved",
        evidence=(),
    )


def _audit() -> dict:
    return {"dropped": [], "dropped_counts": {}}


def test_scope_gate_drops_out_of_scope_and_stamps_scope_id():
    inside = Target("T1", "G06", "p130", "份额类别", "needs_edit", "")
    outside = Target("T2", "G06", "p280", "基金转换", "needs_edit", "")
    audit = _audit()

    _apply_scope_gate([inside, outside], {"G06": _scope("G06", ("p130", "p131"))}, audit)

    assert inside.out_of_scope is False
    assert inside.scope_id == "G06:G06:L01"
    assert outside.out_of_scope is True
    assert "RECALL_TARGET_OUT_OF_SCOPE" in outside.reason
    assert audit["dropped_counts"]["plan:OUT_OF_RULE_SCOPE:G06"] == 1
    assert audit["dropped"] == [
        {"stage": "plan", "code": "OUT_OF_RULE_SCOPE", "rule_id": "G06", "location": "p280"}]


def test_scope_gate_fails_closed_for_unresolved_rule():
    target = Target("T1", "G15", "p800", "销售服务费", "needs_edit", "")
    audit = _audit()

    _apply_scope_gate([target], {"G15": _scope("G15", ())}, audit)

    assert target.out_of_scope is True
    assert "RECALL_TARGET_OUT_OF_SCOPE" in target.reason
    assert audit["dropped_counts"]["plan:OUT_OF_RULE_SCOPE:G15"] == 1


def test_window_rule_scope_with_scopes_skips_unowned_window():
    chunk_a = _Chunk(id="C1", locations=("p130",), text="[p130] x")
    chunk_b = _Chunk(id="C2", locations=("p280",), text="[p280] y")
    blind: list[dict] = []
    sections = [SimpleNamespace(id="S04", locations=("p130",)),
                SimpleNamespace(id="S07", locations=("p280",))]
    rules = [{"rule_id": "G06"}]

    scoped = _window_rule_scope([chunk_a, chunk_b], mapping={"G06": ["S04", "S07"]},
                                sections=sections, rules=rules, mandatory={"G06"},
                                blind_windows=blind,
                                scopes={"G06": _scope("G06", ("p130",))})

    by_id = {chunk.id: ids for chunk, ids in scoped}
    assert by_id == {"C1": {"G06"}, "C2": set()}
    assert blind and blind[0]["skipped"] == "OUT_OF_RULE_SCOPE"


def _inspection() -> SimpleNamespace:
    def span(location: str, section_path: str) -> SimpleNamespace:
        text = "基金销售服务费每日计提，按月支付。"
        segment = SimpleNamespace(start=0, end=len(text))
        return SimpleNamespace(location=location, text=text, zone="body",
                               logical_zone="body", section_path=section_path,
                               segments=(segment,))

    spans = (span("p1", "七、基金费用与税收"), span("p2", "八、基金的收益与分配"))
    by_location = {item.location: item for item in spans}
    return SimpleNamespace(paragraphs=spans,
                           by_location=lambda location: by_location[location])


def test_ensure_delete_targets_only_scans_rule_scope():
    rule = {"rule_id": "G15", "title": "基金费用与税收-销售服务费",
            "operations": [{"op": "delete",
                            "old_text": "基金销售服务费每日计提，按月支付。"}]}
    inspection = _inspection()

    scoped = ensure_delete_targets([], {"G15": rule}, inspection,
                                   scopes={"G15": _scope("G15", ("p1",))})
    legacy = ensure_delete_targets([], {"G15": rule}, inspection)

    assert [target.location for target in scoped] == ["p1"]
    assert {target.location for target in legacy} == {"p1", "p2"}


# ---------------------------------------------------------------------------
# Claim Replay / delete residuals must use the same RuleScope
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
D06 = (ROOT / "funds_word"
       / "广发创业板交易型开放式指数证券投资基金发起式联接基金基金合同_20250319.docx")
SUMMARY_FEE_COPIES = {f"p{number}" for number in range(1286, 1290)}


class _FeeFacts:
    """Minimal verified facts for the deterministic G15/G17 delete fixture."""

    statuses: dict[str, str] = {}
    class_count = 2
    has_service_fee = True
    floating_management_fee = False
    quotes_verified: dict[str, bool] = {}
    current_classes: tuple[str, ...] = ()
    service_group: tuple[str, ...] = ()
    subscription_group: tuple[str, ...] = ()
    ambiguous_classes: tuple[str, ...] = ()

    def status_of(self, name):
        return self.statuses.get(name, "VERIFIED")

    def as_ledger(self):
        return {"class_count": self.class_count}


def _artifact_with_deleted(original, locations):
    changed = {str(location) for location in locations}

    def span(original_span):
        if original_span.location not in changed:
            return original_span
        return SimpleNamespace(location=original_span.location, text="",
                               zone=getattr(original_span, "zone", "body"),
                               logical_zone=getattr(original_span, "logical_zone",
                                                    getattr(original_span, "zone", "body")),
                               section_path=getattr(original_span, "section_path", ""),
                               segments=())

    spans = tuple(span(item) for item in original.paragraphs)
    by_location = {item.location: item for item in spans}
    return SimpleNamespace(paragraphs=spans,
                           by_location=lambda location: by_location[location],
                           source_sha256="d06-scoped-artifact")


def _delete_target(target_id, rule_id, location, text, operation_id):
    return {"target_id": target_id, "rule_id": rule_id, "location": location,
            "quote": text, "state": "needs_edit", "reason": "scope fixture",
            "start": 0, "end": len(text), "resolution": "resolved",
            "segment_ok": True, "composite": [], "operations": [operation_id],
            "claimed_operations": [], "attribution_error": "", "site_candidates": [],
            "occurrence_index": -1, "occurrence_anchor": "", "out_of_scope": False,
            "scope_id": ""}


def _delete_edit(rule_id, target_id, location, text, operation_id):
    return {"rule_id": rule_id, "target_id": target_id, "location": location,
            "start": 0, "end": len(text), "replacement": "", "operation": "delete",
            "operation_keys": [operation_id], "content_source": "guide_text",
            "evidence": {"fixed_text": ""}}


@pytest.fixture(scope="module")
def d06_fee_replay_case():
    from fundlex.docx import inspect_docx
    from fundlex.generation.claim_replay import replay_claims
    from fundlex.obligations import apply_facts, compile_obligations
    from fundlex.recall import structure_index
    from fundlex.rule_scope import resolve_rule_scopes

    assert D06.exists(), D06
    original = inspect_docx(D06)
    sections = structure_index(original)
    text = {number: original.by_location(f"p{number}").text
            for number in (807, 808, 809, 810)}

    g15 = {
        "rule_id": "G15", "title": "基金费用与税收-3、基金销售服务费",
        "section_hint": "基金费用与税收",
        "operations": [{
            "op": "delete", "old_text": text[807],
            "condition": {"kind": "none"}, "operation_id": "G15:0"}],
    }
    # p808/p809 are one split sentence and p810 the following one.  The artifact
    # deletes the body copies p807/p808/p810 (p809 is the untouched continuation).
    g17 = {
        "rule_id": "G17", "title": "基金费用与税收-3、基金销售服务费",
        "section_hint": "基金费用与税收",
        "operations": [
            {"op": "delete", "old_text": text[808] + text[809],
             "condition": {"kind": "none"}, "operation_id": "G17:0"},
            {"op": "delete", "old_text": text[810],
             "condition": {"kind": "none"}, "operation_id": "G17:1"},
        ],
    }
    rules = {"G15": g15, "G17": g17}
    facts = _FeeFacts()
    obligations = compile_obligations({"groups": [g15, g17]})
    apply_facts(obligations, facts)
    scopes = resolve_rule_scopes(
        [{"rule_id": rule_id, "title": "基金费用与税收-3、基金销售服务费"}
         for rule_id in ("G15", "G17")],
        sections, original,
        {"G15": ["S16", "S28"], "G17": ["S16", "S28"]},
    )
    targets = {
        "T15": _delete_target("T15", "G15", "p807", text[807], "G15:0"),
        "T17a": _delete_target("T17a", "G17", "p808", text[808], "G17:0"),
        "T17b": _delete_target("T17b", "G17", "p810", text[810], "G17:1"),
        # Untagged summary targets: replay itself must drop these by scope even if
        # an upstream plan forgot the out_of_scope stamp.
        "T15sum": _delete_target("T15sum", "G15", "p1286",
                                 original.by_location("p1286").text, "G15:0"),
        "T17sum": _delete_target("T17sum", "G17", "p1289",
                                 original.by_location("p1289").text, "G17:1"),
    }
    edits = [
        _delete_edit("G15", "T15", "p807", text[807], "G15:0"),
        _delete_edit("G17", "T17a", "p808", text[808], "G17:0"),
        _delete_edit("G17", "T17b", "p810", text[810], "G17:1"),
    ]
    actual = _artifact_with_deleted(original, ("p807", "p808", "p810"))
    return SimpleNamespace(
        original=original, actual=actual, rules=rules, facts=facts,
        obligations=obligations, scopes=scopes, targets=targets, edits=edits,
        replay_claims=replay_claims,
    )


def _replay(case, scopes):
    return case.replay_claims(
        case.edits, case.original, case.actual, rules_by_id=case.rules,
        facts=case.facts, targets_by_id=case.targets,
        obligations=case.obligations, scopes=scopes)


def _obligation_sites(result):
    return {location for item in (result.get("obligations") or {}).values()
            for location in item.get("sites") or ()}


def test_d06_claim_replay_scope_excludes_summary_fee_copies(d06_fee_replay_case):
    case = d06_fee_replay_case
    for rule_id in ("G15", "G17"):
        scope = case.scopes[rule_id]
        assert scope.resolution == "resolved"
        assert {"p807", "p808", "p810"} <= scope.locations
        assert not (scope.locations & SUMMARY_FEE_COPIES)

    scoped = _replay(case, case.scopes)
    legacy = _replay(case, None)

    assert not (_obligation_sites(scoped) & SUMMARY_FEE_COPIES)
    assert SUMMARY_FEE_COPIES <= _obligation_sites(legacy)
    assert not ({str(item.get("location") or "")
                 for item in scoped.get("failures") or ()} & SUMMARY_FEE_COPIES)
    assert ({str(item.get("location") or "")
             for item in legacy.get("failures") or ()} & SUMMARY_FEE_COPIES)
    # The body copies remain required sites in both modes.
    assert {"p807", "p808", "p810"} <= _obligation_sites(scoped)


def test_unresolved_scope_does_not_fall_back_to_document_scan(d06_fee_replay_case):
    case = d06_fee_replay_case
    unresolved = RuleScope(
        rule_id="G15", leaf_ids=frozenset(), locations=frozenset(), zone="",
        include_summary_copies=False, copy_keys=frozenset(),
        resolution="unresolved", evidence=("test=unresolved",))
    scopes = {**case.scopes, "G15": unresolved}

    result = _replay(case, scopes)
    g15 = [item for item in (result.get("obligations") or {}).values()
           if item.get("rule_id") == "G15"]

    assert g15
    for item in g15:
        assert item.get("sites") == []
        assert item.get("failure_code") == "RULE_SCOPE_UNRESOLVED"
    assert any(item.get("code") == "RULE_SCOPE_UNRESOLVED"
               and item.get("rule_id") == "G15"
               for item in result.get("failures") or ())
    assert not ({str(item.get("location") or "")
                 for item in result.get("failures") or ()} & SUMMARY_FEE_COPIES)


def test_delete_residuals_scope_excludes_summary_fee_copies(d06_fee_replay_case):
    from fundlex.generation.claim_replay import check_delete_residuals

    case = d06_fee_replay_case

    def residuals(scopes):
        return check_delete_residuals(
            case.rules, case.actual, edits=case.edits, original=case.original,
            targets=list(case.targets.values()), facts=case.facts,
            obligations=case.obligations, scopes=scopes)

    scoped = residuals(case.scopes)
    legacy = residuals(None)
    scoped_locations = {str(item.get("location") or "") for item in scoped}
    legacy_locations = {str(item.get("location") or "") for item in legacy}

    assert not (scoped_locations & SUMMARY_FEE_COPIES)
    assert "p1289" in legacy_locations
    assert "p1286" in legacy_locations
