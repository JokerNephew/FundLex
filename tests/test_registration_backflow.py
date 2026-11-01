"""FL-D1001 注册回流 mutation 反例（无模型，进 CI）。

语义锁定：
* 认证解析产物（带声明 operation_id）ensure 后全部入册且全事实 VERIFIED 下可路由；
* 既有注册条（内置/发布方）**绝不覆盖**；
* 未发布档位映射的 op kind 继续 fail-closed（gaps 报出，不入册）;
* ensure 幂等（二次调用 registered 为空、adopted 记既有）。
"""
from __future__ import annotations

import hashlib
import json

import pytest

from fundlex.generation import registry as reg
from fundlex.generation.registry import (OPERATION_REGISTRY,
                                         ensure_registered_operations,
                                         derive_operation_spec,
                                         operation_registry_coverage_gaps)
from fundlex.generation.router import route_operation
from fundlex.generation.types import GenerationTier as T
from fundlex.guide import certify_guide_document


def _doc(rule_id: str, operations: list[dict]) -> dict:
    rule = {"rule_id": rule_id, "title": rule_id, "section_hint": "释义",
            "requirement": "r", "operations": operations,
            "old_text_variants": [], "slot_tokens": [], "class_substitution": False,
            "references": [], "source_paragraphs": [], "notes": ""}
    sha = hashlib.sha256(rule_id.encode()).hexdigest()
    doc = {"schema_version": "guide-rules-v1", "source_sha256": sha, "groups": [rule],
           "validation": {"errors": [], "warnings": [], "coverage_gaps": [],
                          "verification": {"findings": [], "invalid_findings": 0}}}
    return certify_guide_document(doc, source_sha256=sha)


def _op(op: str, key: str, condition: dict | None = None) -> dict:
    return {"op": op, "old_text": "旧", "new_text": "新",
            "condition": condition or {"kind": "none", "value": None},
            "operation_id": key, "group_kind": "INDEPENDENT", "one_of_group": ""}


@pytest.fixture(autouse=True)
def registry_checkpoint():
    """前后均还原为出厂注册表——FL-D1001 后 process_recall_first 会对任何测试
    指引做注册回流（进程级、幂等属设计），套件内测试间共享该注册面，本文件
    一律从纯净内置注册表起跳，避免与他测试的指引件相互污染。"""
    OPERATION_REGISTRY.clear()
    OPERATION_REGISTRY.update(reg._build_operation_registry())
    yield
    OPERATION_REGISTRY.clear()
    OPERATION_REGISTRY.update(reg._build_operation_registry())


def test_parsed_doc_registers_and_routes(registry_checkpoint):
    doc = _doc("RX1", [_op("replace", "RX1:0"),
                       _op("delete", "RX1:1",
                           {"kind": "has_service_fee", "value": True})])
    assert operation_registry_coverage_gaps(doc) == ["RX1:0", "RX1:1"]
    result = ensure_registered_operations(doc)
    assert result["registered"] == ["RX1:0", "RX1:1"]
    assert result["gaps"] == []
    assert operation_registry_coverage_gaps(doc) == []
    # 全事实 VERIFIED 下两 op 均可路由且档位=保守默认
    decision = route_operation("RX1:0", fact_status={}, structure=None)
    assert not decision.blocked
    spec = OPERATION_REGISTRY["RX1:0"]
    assert spec.default_tier == T.SPLICE and spec.mode == "replace"
    cond_spec = OPERATION_REGISTRY["RX1:1"]
    assert cond_spec.default_tier == T.DELETE
    assert cond_spec.condition_kind == "has_service_fee" and cond_spec.condition_value is True


def test_builtin_entries_never_overwritten(registry_checkpoint):
    builtin_before = OPERATION_REGISTRY["G01:0"]
    doc = _doc("G01", [_op("append", "G01:0")])
    result = ensure_registered_operations(doc)
    assert result["registered"] == []
    assert result["adopted"] == ["G01:0"]
    assert OPERATION_REGISTRY["G01:0"] is builtin_before


def test_unmappable_op_kind_fails_closed(registry_checkpoint):
    # 未发布档位映射的 op kind：派生返回 None、键不入册、仍报 gap。
    # （认证层连 schema 都不会放行该 kind——这里用原始 dict 测闸门自身的兜底。）
    assert derive_operation_spec("RX2", 0, {"op": "warp"}) is None
    doc_warp = {"groups": [{"rule_id": "RXW",
                            "operations": [{"op": "warp", "operation_id": "RXW:0"}]}]}
    result = ensure_registered_operations(doc_warp)
    assert result["gaps"] == ["RXW:0"]
    assert "RXW:0" not in OPERATION_REGISTRY
    # 正常对照案不受影响
    doc = _doc("RX2", [_op("append", "RX2:0")])
    assert ensure_registered_operations(doc)["registered"] == ["RX2:0"]


def test_non_positional_publisher_key_keeps_controlled_gate(registry_checkpoint):
    """非位置型发布方键（G99:CUSTOM）：不属于解析流水线身份形态，
    回流不派生，elements 保留受控发布方闸（既有契约不动）。"""
    doc = {"groups": [{"rule_id": "G99",
                       "operations": [{"op": "replace", "operation_id": "G99:CUSTOM",
                                       "condition": {"kind": "none"},
                                       "group_kind": "INDEPENDENT"}]}]}
    result = ensure_registered_operations(doc)
    # 两闸一致如实报缺失，键不入册（受控发布方路径不受影响）
    assert result["gaps"] == ["G99:CUSTOM"]
    assert "G99:CUSTOM" not in OPERATION_REGISTRY
    assert operation_registry_coverage_gaps(doc) == ["G99:CUSTOM"]


def test_ensure_is_idempotent(registry_checkpoint):
    doc = _doc("RX3", [_op("append", "RX3:0")])
    first = ensure_registered_operations(doc)
    second = ensure_registered_operations(doc)
    assert first["registered"] == ["RX3:0"]
    assert second["registered"] == [] and second["adopted"] == ["RX3:0"]


def test_positional_keys_for_generated_identity(registry_checkpoint):
    # 真实解析流水线路径：bind_operation_identities 先生成位置 id → 认证 → 入册
    from fundlex.guide import bind_operation_identities
    operation = _op("delete", "")
    operation.pop("operation_id")
    rule = {"rule_id": "RX4", "title": "RX4", "section_hint": "释义",
            "requirement": "r", "operations": [operation],
            "old_text_variants": [], "slot_tokens": [], "class_substitution": False,
            "references": [], "source_paragraphs": [], "notes": ""}
    sha = hashlib.sha256(b"RX4").hexdigest()
    doc = {"schema_version": "guide-rules-v1", "source_sha256": sha, "groups": [rule],
           "validation": {"errors": [], "warnings": [], "coverage_gaps": [],
                          "verification": {"findings": [], "invalid_findings": 0}}}
    bind_operation_identities(doc)
    assert doc["groups"][0]["operations"][0]["operation_id"] == "RX4:0"
    assert doc["groups"][0]["operations"][0]["operation_id_generated"] is True
    certified = certify_guide_document(doc, source_sha256=sha)
    result = ensure_registered_operations(certified)
    assert result["registered"] == ["RX4:0"]
    assert "RX4:0" in OPERATION_REGISTRY


def test_generated_extension_under_builtin_rule_no_longer_evasp(registry_checkpoint):
    """黄金集镜像 mutation：内置规则名下的解析扩展 op（generated id，如 G02:2）
    修复前既绕 gate 又在运行时崩（gate≠runtime）；修复后闸口如实报 gap，
    backflow 入册+可路由。"""
    doc_warp = {"groups": [{"rule_id": "G02",
                            "operations": [
                                {"op": "replace", "operation_id": "G02:2",
                                 "operation_id_generated": True,
                                 "condition": {"kind": "none", "value": None},
                                 "group_kind": "INDEPENDENT", "one_of_group": ""}]}]}
    assert operation_registry_coverage_gaps(doc_warp) == ["G02:2"]
    result = ensure_registered_operations(doc_warp)
    assert result["registered"] == ["G02:2"]
    assert operation_registry_coverage_gaps(doc_warp) == []
    decision = route_operation("G02:2", fact_status={}, structure=None)
    assert not decision.blocked
    # 内置既有条不受污染
    assert OPERATION_REGISTRY["G02:0"].default_tier is not None


def test_truly_legacy_ops_on_known_rule_stay_legacy(registry_checkpoint):
    """无声明 id 的内置规则 op：保持 legacy 兼容路径（gate 不报 gap，
    运行时走低层执行器），此契约不随 FL-D1001 改变。"""
    doc_legacy = {"groups": [{"rule_id": "G05",
                              "operations": [{"op": "delete", "old_text": "备案句",
                                              "condition": {"kind": "none"}}]}]}
    assert operation_registry_coverage_gaps(doc_legacy) == []
