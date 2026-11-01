"""FL-D921 回归：语义审计 PASS 清障仅限效果类失败码，结构完整性码永久留存。"""
from __future__ import annotations

from fundlex.generation.claim_replay import (
    _STRUCTURAL_INTEGRITY_CODES,
    _purge_audited_failures,
)


def _state_verdict(verdict: str) -> dict[str, dict[str, str]]:
    return {"OB-1": {"state": verdict}}


def test_effect_class_failure_retired_when_obligation_passes() -> None:
    failures = [
        {"code": "CLAIM_OPERATION_UNPROVEN", "obligation_id": "OB-1"},
        {"code": "CLAIM_OPERATION_APPLICABILITY_UNPROVEN", "obligation_id": "OB-1"},
    ]
    _purge_audited_failures(failures, _state_verdict("PASS"))
    assert failures == []


def test_structural_failures_survive_an_audit_pass() -> None:
    survivors = [
        {"code": "CLAIM_OPERATION_SPAN_UNAUTHORIZED", "obligation_id": "OB-1"},
        {"code": "CLAIM_OCCURRENCE_MISMATCH", "obligation_id": "OB-1"},
        {"code": "OUTSIDE_SPAN_CHANGED", "obligation_id": "OB-1"},
    ]
    original = list(survivors)
    _purge_audited_failures(survivors, _state_verdict("PASS"))
    # 白名单外的结构码（OUTSIDE_SPAN_CHANGED 不带前缀）仍按旧口径处理；白名单内永存。
    codes = [item["code"] for item in survivors]
    assert "CLAIM_OPERATION_SPAN_UNAUTHORIZED" in codes
    assert "CLAIM_OCCURRENCE_MISMATCH" in codes
    assert "OUTSIDE_SPAN_CHANGED" not in codes
    assert len(original) == 3


def test_every_structural_code_in_the_allowlist_survives() -> None:
    failures = [{"code": code, "obligation_id": "OB-1"}
                for code in sorted(_STRUCTURAL_INTEGRITY_CODES)]
    _purge_audited_failures(failures, _state_verdict("PASS"))
    assert len(failures) == len(_STRUCTURAL_INTEGRITY_CODES)


def test_unresolved_obligation_keeps_everything() -> None:
    failures = [
        {"code": "CLAIM_OPERATION_SPAN_UNAUTHORIZED", "obligation_id": "OB-1"},
        {"code": "CLAIM_OPERATION_UNPROVEN", "obligation_id": "OB-1"},
    ]
    _purge_audited_failures(failures, _state_verdict("FAIL"))
    assert len(failures) == 2


def test_failure_code_field_alias_is_honoured() -> None:
    failures = [{"failure_code": "CLAIM_OPERATION_SPAN_UNAUTHORIZED",
                 "obligation_id": "OB-1"}]
    _purge_audited_failures(failures, _state_verdict("PASS"))
    assert len(failures) == 1
