"""FL-D931 回归：通用解析指令不再携带内置指引专属的 15 组人读暗示。

判词 B9 配套 FL-D898 质量门实测：一份*新形态*指引（条款式编号结构、3 组、
与内置 22/15 组形态完全不同）必须能被 build_guide_document 完整解析并认证，
且 prompt 不得出现任何固定组数暗示。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fundlex.guide import (_BUILTIN_GUIDE_COMPANION_NOTE, extract_guide_source,
                           build_guide_document)
from tests.test_guide import build_docx, clean_verification


NEW_SHAPE_PARAGRAPHS: list[tuple[str, str]] = [
    ("某基金合同条款修改指引（条款式）", "bold"),
    ("第一条 销售服务费表述", "bold"),
    ("原条款：销售服务费按年计提。", "plain"),
    ("新条款：销售服务费按月计提。", "plain"),
    ("第二条 备案表述", "bold"),
    ("删除“并报中国证监会备案”。", "plain"),
    ("第三条 风险评级条款", "bold"),
    ("保持风险评级相关条款不变。", "plain"),
]


def new_shape_parsed() -> dict:
    result = {
        "groups": [
            {
                "rule_id": "G01",
                "title": "第一条 销售服务费表述",
                "section_hint": "基金费用与税收",
                "requirement": "把销售服务费计提口径由按年改为按月。",
                "operations": [{"op": "replace", "old_text": "销售服务费按年计提。",
                                "new_text": "销售服务费按月计提。",
                                "condition": {"kind": "none", "value": None}}],
                "old_text_variants": [],
                "slot_tokens": [],
                "class_substitution": False,
                "references": [],
                "source_paragraphs": [0, 1, 2, 3],
                "notes": "",
            },
            {
                "rule_id": "G02",
                "title": "第二条 备案表述",
                "section_hint": "基金的基本情况",
                "requirement": "删除备案句。",
                "operations": [{"op": "delete", "old_text": "并报中国证监会备案",
                                "condition": {"kind": "none", "value": None}}],
                "old_text_variants": [],
                "slot_tokens": [],
                "class_substitution": False,
                "references": [],
                "source_paragraphs": [4, 5],
                "notes": "",
            },
            {
                "rule_id": "G03",
                "title": "第三条 风险评级条款",
                "section_hint": "释义",
                "requirement": "本组条款保持原样，不做修改。",
                "operations": [{"op": "noop", "text": "保持风险评级相关条款不变。",
                                "condition": {"kind": "none", "value": None}}],
                "old_text_variants": [],
                "slot_tokens": [],
                "class_substitution": False,
                "references": [],
                "source_paragraphs": [6, 7],
                "notes": "",
            },
        ],
        "notes": "new-shape numbered guide",
    }
    for group in result["groups"]:
        for operation in group["operations"]:
            operation["group_kind"] = "INDEPENDENT"
            operation["one_of_group"] = ""
    return result


class CapturingGateway:
    def __init__(self, outcomes: list[object]):
        self.outcomes = list(outcomes)
        self.model = "capture-guide"
        self.max_context_chars = 200000
        self.instructions: list[str] = []
        self.events: list[dict] = []

    def call(self, *, task_type, bounded_context, response_schema, instruction,
             prompt_version="v1"):
        self.instructions.append(instruction)
        self.events.append({"task_type": task_type, "prompt_version": prompt_version})
        outcome = self.outcomes.pop(0)
        return SimpleNamespace(value=outcome, model=self.model, latency_ms=1,
                               prompt_tokens=10, completion_tokens=10, total_tokens=20,
                               request_id="req-x", attempts=1, estimated_cost_usd=0.0,
                               task_type=task_type)

    def metrics(self) -> dict:
        return {"logical_calls": 0, "http_attempts": 0, "checkpoint_reuses": 0,
                "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                "latency_ms": 0, "rate_limit_count": 0, "error_count": 0,
                "estimated_cost_usd": 0.0, "events": list(self.events)}


def test_new_shape_guide_parses_without_any_group_count_hint(tmp_path: Path) -> None:
    path = build_docx(tmp_path / "new_shape.docx", NEW_SHAPE_PARAGRAPHS)
    source = extract_guide_source(path)
    gateway = CapturingGateway([new_shape_parsed(), clean_verification()])
    document = build_guide_document(source, gateway)
    assert document["certification"]["approved"] is True, document["certification"]
    assert len(document["groups"]) == 3
    parse_instruction = gateway.instructions[0]
    assert "15-group" not in parse_instruction
    assert "22-group" not in parse_instruction
    assert "group count" in parse_instruction  # 仅负向约束（勿按预期组数硬推）


def test_companion_note_only_appended_for_builtin(tmp_path: Path) -> None:
    path = build_docx(tmp_path / "new_shape.docx", NEW_SHAPE_PARAGRAPHS)
    source = extract_guide_source(path)
    gateway = CapturingGateway([new_shape_parsed(), clean_verification()])
    build_guide_document(source, gateway, companion_note=_BUILTIN_GUIDE_COMPANION_NOTE)
    assert gateway.instructions[0].endswith(_BUILTIN_GUIDE_COMPANION_NOTE)


def test_builtin_note_not_in_default_parse(tmp_path: Path) -> None:
    path = build_docx(tmp_path / "new_shape.docx", NEW_SHAPE_PARAGRAPHS)
    source = extract_guide_source(path)
    gateway = CapturingGateway([new_shape_parsed(), clean_verification()])
    build_guide_document(source, gateway)
    assert _BUILTIN_GUIDE_COMPANION_NOTE not in gateway.instructions[0]
    assert "15-group" not in gateway.instructions[0]
