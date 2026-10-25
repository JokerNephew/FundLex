"""G15 owns only an immediate source-proven payment delay tail (FL-D216)."""
import pytest

from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import g15_delay_continuation_targets
from fundlex.recall_pipeline import _plan_and_generate
from test_g15_payment_delay_boundary import PAYMENT, DELAY, CHECK, NoModel, _rule, _target, _write
from test_recall_core import _facts

USAGE = "销售服务费主要用于支付销售机构佣金。"
REAL_DELAY = "若遇法定节假日、休息日或不可抗力致使无法按时支付等，支付日期顺延。"


def test_actual_docx_tail_is_deleted_and_unplanned_tail_fails_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    source = tmp_path / "source.docx"
    original = _write(source, [PAYMENT, REAL_DELAY + USAGE, CHECK, PAYMENT, REAL_DELAY + USAGE])
    rule, facts = _rule(), _facts()
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    targets = [_target("p0", PAYMENT), _target("p3", PAYMENT)]
    planned, _, _, _, actual = _plan_and_generate(NoModel(), {"G15": rule}, targets,
        original, facts, source, tmp_path, max_compose_calls=0, obligations=ledger)
    assert len(planned["edits"]) == 4, planned["ledger"]
    assert actual.by_location("p0").text == actual.by_location("p3").text == ""
    assert actual.by_location("p1").text == actual.by_location("p4").text == USAGE
    assert actual.by_location("p2").text == CHECK
    proof = replay_claims(planned["edits"], original, actual, rules_by_id={"G15": rule},
        facts=facts, obligations=ledger, targets_by_id={t.target_id: t.as_dict() for t in targets})
    assert proof["verified"], proof["failures"]
    # Omit both tail targets as well as their edits: closure must reread source.
    missing = _write(tmp_path / "missing.docx", ["", REAL_DELAY + USAGE, CHECK, "", REAL_DELAY + USAGE])
    rejected = replay_claims([e for e in planned["edits"] if e["location"] in {"p0", "p3"}],
        original, missing, rules_by_id={"G15": rule}, facts=facts, obligations=ledger,
        targets_by_id={t.target_id: t.as_dict() for t in targets if t.location in {"p0", "p3"}})
    assert not rejected["verified"]
    sites = [s for result in rejected["obligations"].values() for s in result["site_effects"]]
    assert all(any(s["location"] == loc and s["state"] == "FAIL" for s in sites) for loc in ("p1", "p4"))


def test_delay_tail_authorization_includes_only_trailing_whitespace(tmp_path):
    """A composite whole-paragraph slice may include source trailing whitespace."""
    source = _write(tmp_path / "source.docx", [PAYMENT, REAL_DELAY + USAGE,
                                                 PAYMENT, REAL_DELAY + "  "])
    original = source
    target = _target("p2", PAYMENT)
    added = g15_delay_continuation_targets([target], {"G15": _rule()}, original)
    assert len(added) == 1
    assert added[0].location == "p3"
    assert added[0].end == len(original.by_location("p3").text)


def test_composite_payment_head_and_delay_replay_as_one_authorized_delete(tmp_path):
    """Replay must reprove both parts of a split payment deletion from source."""
    from fundlex.recall import compact_offsets

    head = "C 类基金份额的基金销售服务费每日计算，逐日累计至每月月末，按月支付，"
    tail = ("由基金管理人与基金托管人核对一致后，基金托管人按照与基金管理人协商一致的方式于"
            "次月首日起5个工作日内从基金财产中一次性支付给基金管理人。若遇法定节假日、公休假等，"
            "支付日期顺延。  ")
    original = _write(tmp_path / "source.docx", [head, tail])
    actual = _write(tmp_path / "actual.docx", ["", ""])
    rule = _rule()
    head_compact, _ = compact_offsets(head)
    tail_compact, _ = compact_offsets(tail)
    visible_tail = tail.rstrip()
    visible_tail_compact, _ = compact_offsets(visible_tail)
    parts = [f"p0:0:{len(head_compact)}", f"p1:0:{len(visible_tail_compact)}"]
    edits = [
        {"target_id": "Y", "rule_id": "G15", "location": "p0", "start": 0,
         "end": len(head), "replacement": "", "operation": "replace",
         "content_source": "composite_delete", "operation_keys": ["G15:0"],
         "expected_old_text": head,
         "evidence": {"composite": True, "parts": parts, "part_index": 0}},
        {"target_id": "Y", "rule_id": "G15", "location": "p1", "start": 0,
         "end": len(tail), "replacement": "", "operation": "replace",
         "content_source": "composite_delete", "operation_keys": ["G15:0"],
         "expected_old_text": tail,
         "evidence": {"composite": True, "parts": parts, "part_index": 1}},
    ]
    proof = replay_claims(edits, original, actual, rules_by_id={"G15": rule})
    assert proof["verified"], proof["failures"]


@pytest.mark.parametrize("head,tail", [
    (PAYMENT + CHECK, DELAY + USAGE),
    (PAYMENT.replace("销售服务费", "管理费"), DELAY + USAGE),
    (PAYMENT, "若遇法定节假日，管理费支付日期顺延。" + USAGE),
    (PAYMENT, "若遇法定节假日，赎回款支付日期顺延。" + USAGE),
    (PAYMENT, CHECK + DELAY),
    (PAYMENT, "若遇法定节假日，支付日期不顺延。" + USAGE),
])
def test_other_mechanisms_and_intervening_clauses_do_not_gain_authorization(tmp_path, head, tail):
    original = _write(tmp_path / "source.docx", [head, tail])
    assert not g15_delay_continuation_targets([_target("p0", head)], {"G15": _rule()}, original)


def test_custom_no_delay_authorization_does_not_bind_tail(tmp_path):
    rule = _rule()
    rule["operations"][0]["old_text"] = PAYMENT
    original = _write(tmp_path / "source.docx", [PAYMENT, DELAY + USAGE])
    assert not g15_delay_continuation_targets([_target("p0", PAYMENT)], {"G15": rule}, original)


@pytest.mark.parametrize("tamper", ["head", "authorization", "boundary", "missing_head"])
def test_replay_recomputes_tail_authority_even_with_forged_evidence(tmp_path, tamper):
    rule = _rule()
    head = PAYMENT if tamper != "head" else PAYMENT.replace("销售服务费", "托管费")
    if tamper == "authorization":
        rule["operations"][0]["old_text"] = PAYMENT
    before = [head, REAL_DELAY + USAGE] if tamper != "missing_head" else [REAL_DELAY + USAGE]
    original = _write(tmp_path / "source.docx", before)
    location = "p1" if tamper != "missing_head" else "p0"
    end = len(REAL_DELAY + USAGE) if tamper == "boundary" else len(REAL_DELAY)
    edit = dict(target_id="forged", rule_id="G15", location=location, start=0, end=end,
        replacement="", operation="replace", content_source="g15_delay_delete",
        operation_keys=["G15:0"], expected_old_text=before[-1][:end],
        evidence={"strategy": "source_payment_delay_continuation", "deleted_quote": before[-1][:end]})
    changed = before[:-1] + [before[-1][end:]]
    actual = _write(tmp_path / "actual.docx", changed)
    proof = replay_claims([edit], original, actual, rules_by_id={"G15": rule})
    assert not proof["verified"]
    assert any(f["code"] == "CLAIM_OPERATION_SPAN_UNAUTHORIZED" for f in proof["failures"])
