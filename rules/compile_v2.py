"""Compile the executable v2 semantic contracts from the frozen v1 source guidance.

The v1 package keeps fixed templates and stays read-only. The v2 package turns the
same source guidance into explicit contracts: allowed changes, must-preserve facts,
dependencies, refusal conditions and code/model checks. Human-authored semantics
live here; the emitted JSON is validated by ``fundlex.rules_v2`` on load.

Run::

    .venv\\Scripts\\python.exe -X utf8 rules\\compile_v2.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1_PATH = ROOT / "rules" / "rules_v1.json"
V2_PATH = ROOT / "rules" / "rules_v2.json"

# Authored per-action contracts. Every key below was checked against the v1
# source guidance (templates + source_provenance) before registration; actions
# without a complete contract are deliberately absent and stay unsupported.
CONTRACTS: dict[str, dict] = {
    "R01-A1": {
        "semantics": {
            "subject": "投资者与基金管理人（直销机构）之间的费用豁免关系",
            "action": "在原份额类别定义段落之后追加直销机构费用豁免及持续持有超一年销售服务费停止收取条款",
            "condition": "仅当合同证据证明所有类别分别属于申购费组（收申购费、不计提销售服务费）或销售服务费组（不收申购费、计提销售服务费）时适用；存在混合类别或证据不足时拒绝",
            "fee_terms": "不新增具体费率、数字或比例；类别名称与费用归属只能来自当前合同证据",
            "ownership": "销售服务费仍归属基金资产；条款只涉及直销机构豁免及销售机构持续持有超一年后不再收取",
            "allowed_changes": [
                "在目标定义段落末尾追加一段新条款",
                "用当前合同实际类别替换参考文案中的 A/C 字样",
            ],
            "must_preserve": [
                "原份额类别定义段落逐字保留，不做任何删除或改写",
                "其他章节、编号、目录、表格与部件不得改动",
            ],
            "forbidden_additions": [
                "不得新增未经证据支持的费率、比例、期限或渠道条件",
                "不得把混合收费类别强行归入申购费组或销售服务费组",
                "不得按合同名称、文件名或样本编号选择类别",
            ],
            "unsupported": ["类别证据不足", "收费属性混合或未知", "目标段落存在结构屏障"],
        },
        "locate": {
            "mode": "class_definition",
            "section": "class_definition",
            "require_class_letters_min": 2,
            "require_any": ["将基金份额分为", "分为不同的类别"],
        },
        "generation": {
            "mode": "generate",
            "kind": "direct_sales_clause",
            "instruction": (
                "以 REFERENCE_TEXT 为句式参考，为当前合同实际类别生成直销机构费用豁免及持续持有超一年"
                "服务费停止收取条款。必须使用 PROFILE_FACTS 中全部类别名称逐一点名，禁止使用不在当前"
                "合同类别集合中的类别字母；禁止新增费率、比例或数字；只生成要追加的条款正文，"
                "不得改写或重复原定义段落。source_quote 必须逐字等于 CONTRACT_SOURCE 内容。changes[].basis_requirement 只能使用 RULE_REQUIREMENTS 中列出的 id，或不提供该字段。"
            ),
            "reference_text": (
                "投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金A类基金份额时，"
                "不收取认购/申购费用；通过直销机构申购的C类基金份额，不收取销售服务费。"
                "对于投资者通过直销机构之外的其他销售机构申购的C类基金份额且持续持有期限超过一年的，"
                "不再继续收取销售服务费。"
            ),
            "max_chars": 400,
        },
        "requirements": [
            {"id": "R01-REQ-1", "kind": "must_state",
             "text": "通过直销机构申购申购费组类别时不收取认购/申购费用，且逐一点名当前合同全部申购费组类别",
             "check": {"kind": "direct_sales_clause", "part": "subscription_group"},
             "verification": "code"},
            {"id": "R01-REQ-2", "kind": "must_state",
             "text": "通过直销机构申购销售服务费组类别时不收取销售服务费，且逐一点名当前合同全部销售服务费组类别",
             "check": {"kind": "direct_sales_clause", "part": "service_group"},
             "verification": "code"},
            {"id": "R01-REQ-3", "kind": "must_state",
             "text": "通过直销机构之外的其他销售机构申购销售服务费组类别且持续持有期限超过一年的，不再继续收取销售服务费",
             "check": {"kind": "direct_sales_clause", "part": "long_holding"},
             "verification": "code"},
            {"id": "R01-REQ-4", "kind": "must_not_state",
             "text": "不得出现合同类别之外的类别字母，不得出现具体费率数字",
             "check": {"kind": "classes_within_profile_and_no_digits"},
             "verification": "code"},
            {"id": "R01-REQ-5", "kind": "must_preserve",
             "text": "新文不得出现具体费率数字，除直销豁免与超过一年停止收取外不得设置其他条件",
             "check": {"kind": "semantic_review"},
             "verification": "model"},
        ],
        "model_verification": ["R01-REQ-5"],
    },
    "R02-A1": {
        "semantics": {
            "subject": "投资者与基金管理人（直销机构）之间的费用豁免关系",
            "action": "在基本情况份额类别定义段落之后追加直销售费用豁免及持续持有超一年销售服务费停止收取条款",
            "condition": "仅当合同证据证明所有类别分别属于申购费组或销售服务费组时适用；混合或证据不足拒绝",
            "fee_terms": "不新增具体费率、数字或比例；类别名称与费用归属只能来自当前合同证据",
            "ownership": "销售服务费仍归属基金资产；条款只涉及直销机构豁免及销售机构持续持有超一年后不再收取",
            "allowed_changes": [
                "在目标定义段落末尾追加一段新条款",
                "用当前合同实际类别替换参考文案中的 A/C 字样",
            ],
            "must_preserve": [
                "原份额类别定义段落逐字保留，不做任何删除或改写",
                "其他章节、编号、目录、表格与部件不得改动",
            ],
            "forbidden_additions": [
                "不得新增未经证据支持的费率、比例、期限或渠道条件",
                "不得把混合收费类别强行归入申购费组或销售服务费组",
                "不得按合同名称、文件名或样本编号选择类别",
            ],
            "unsupported": ["类别证据不足", "收费属性混合或未知", "目标段落存在结构屏障"],
        },
        "locate": {
            "mode": "class_definition",
            "section": "class_definition",
            "require_class_letters_min": 2,
            "require_any": ["将基金份额分为", "分为不同的类别"],
        },
        "generation": {
            "mode": "generate",
            "kind": "direct_sales_clause",
            "instruction": (
                "以 REFERENCE_TEXT 为句式参考，为当前合同实际类别生成直销机构费用豁免及持续持有超一年"
                "服务费停止收取条款。必须使用 PROFILE_FACTS 中全部类别名称逐一点名，禁止使用不在当前"
                "合同类别集合中的类别字母；禁止新增费率、比例或数字；只生成要追加的条款正文，"
                "不得改写或重复原定义段落。source_quote 必须逐字等于 CONTRACT_SOURCE 内容。changes[].basis_requirement 只能使用 RULE_REQUIREMENTS 中列出的 id，或不提供该字段。"
            ),
            "reference_text": (
                "投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金A类基金份额时，"
                "不收取认购/申购费用；通过直销机构申购的C类基金份额，不收取销售服务费。"
                "对于投资者通过直销机构之外的其他销售机构申购的C类基金份额且持续持有期限超过一年的，"
                "不再继续收取销售服务费。"
            ),
            "max_chars": 400,
        },
        "requirements": [
            {"id": "R02-REQ-1", "kind": "must_state",
             "text": "通过直销机构申购申购费组类别时不收取认购/申购费用，且逐一点名当前合同全部申购费组类别",
             "check": {"kind": "direct_sales_clause", "part": "subscription_group"},
             "verification": "code"},
            {"id": "R02-REQ-2", "kind": "must_state",
             "text": "通过直销机构申购销售服务费组类别时不收取销售服务费，且逐一点名当前合同全部销售服务费组类别",
             "check": {"kind": "direct_sales_clause", "part": "service_group"},
             "verification": "code"},
            {"id": "R02-REQ-3", "kind": "must_state",
             "text": "通过直销机构之外的其他销售机构申购销售服务费组类别且持续持有期限超过一年的，不再继续收取销售服务费",
             "check": {"kind": "direct_sales_clause", "part": "long_holding"},
             "verification": "code"},
            {"id": "R02-REQ-4", "kind": "must_not_state",
             "text": "不得出现合同类别之外的类别字母，不得出现具体费率数字",
             "check": {"kind": "classes_within_profile_and_no_digits"},
             "verification": "code"},
            {"id": "R02-REQ-5", "kind": "must_preserve",
             "text": "新文不得出现具体费率数字，除直销豁免与超过一年停止收取外不得设置其他条件",
             "check": {"kind": "semantic_review"},
             "verification": "model"},
        ],
        "model_verification": ["R02-REQ-5"],
    },
    "R03-A3": {
        "semantics": {
            "subject": "份额类别设置段落中的备案语句",
            "action": "删除“并报中国证监会备案”短语，保留同句其他内容",
            "condition": "仅限基金的基本情况/份额类别设置范围内出现该短语时适用",
            "fee_terms": None,
            "ownership": None,
            "allowed_changes": ["删除目标短语本身"],
            "must_preserve": ["同段其余文字、编号、标点及其他章节内同短语不得改动"],
            "forbidden_additions": ["不得新增任何文字"],
            "unsupported": ["跨段目标", "跨 cell 目标", "结构屏障", "同位置无法唯一定位"],
        },
        "locate": {
            "mode": "code_literal",
            "triggers": ["并报中国证监会备案"],
            "boundary": {
                "trim_whitespace": True,
                "require_source_sentence_boundary": False,
            },
        },
        "generation": {"mode": "delete", "max_chars": 0},
        "requirements": [
            {"id": "R03-REQ-1", "kind": "must_not_state",
             "text": "目标范围内不得残留“并报中国证监会备案”",
             "check": {"kind": "delete_only"},
             "verification": "code"},
            {"id": "R03-REQ-2", "kind": "must_preserve",
             "text": "仅删除该短语；同段其他文字与文档其他部分逐字保留",
             "check": {"kind": "boundary_scope", "boundary": "preserve_outside"},
             "verification": "code"},
        ],
        "model_verification": [],
    },
    "R04-A1": {
        "semantics": {
            "subject": "份额类别设置中的类别互相转换禁止句",
            "action": "删除不同份额类别之间不得互相转换的完整原句",
            "condition": "仅适用于基金的基本情况/份额类别设置；需多类别份额",
            "fee_terms": None,
            "ownership": None,
            "allowed_changes": ["删除目标完整句"],
            "must_preserve": ["同段其他句式、编号与转换业务章节内容不得改动"],
            "forbidden_additions": ["不得新增任何文字"],
            "unsupported": ["跨段目标", "转换业务章节或其他区域", "结构屏障", "范围无法唯一确认"],
        },
        "locate": {
            "mode": "code_recognition",
            "recognition_kind": "conversion_prohibition",
            "boundary": {
                "trim_whitespace": True,
                "require_sentence_span": True,
            },
        },
        "generation": {"mode": "delete", "max_chars": 0},
        "requirements": [
            {"id": "R04-REQ-1", "kind": "must_not_state",
             "text": "目标句已删除，其他文本保留",
             "check": {"kind": "delete_only"},
             "verification": "code"},
            {"id": "R04-REQ-2", "kind": "must_preserve",
             "text": "只删除完整目标句；转换业务章节及同段其他内容逐字保留",
             "check": {"kind": "boundary_scope", "boundary": "preserve_outside"},
             "verification": "code"},
        ],
        "model_verification": [],
    },
    "R11-A1": {
        "semantics": {
            "subject": "费率调整段落中的短期持有赎回费旧句",
            "action": "删除持续持有期少于 7 日收取不低于 1.5% 赎回费并全额计入基金财产的旧句",
            "condition": "仅限申购与赎回价格费用章节的费率调整类宿主段落；费用归属段由 R10 处理",
            "fee_terms": "删除旧费率句；不得改动其他费率数字",
            "ownership": None,
            "allowed_changes": ["删除目标完整句"],
            "must_preserve": ["宿主段落中的费率调整语句、费率数字与其他文本不得改动"],
            "forbidden_additions": ["不得新增任何文字"],
            "unsupported": ["费用归属段（属 R10）", "结构屏障", "宿主段落不明确", "变体无法确认"],
        },
        "locate": {
            "mode": "code_recognition",
            "recognition_kind": "short_holding_redemption",
            "host_policy": "fee_rate_or_adjustment",
            "boundary": {
                "trim_whitespace": True,
                "require_sentence_span": True,
            },
        },
        "generation": {"mode": "delete", "max_chars": 0},
        "requirements": [
            {"id": "R11-REQ-1", "kind": "must_not_state",
             "text": "费率调整段中的短期持有赎回费旧句已删除",
             "check": {"kind": "delete_only"},
             "verification": "code"},
            {"id": "R11-REQ-2", "kind": "must_preserve",
             "text": "宿主段落费率调整内容逐字保留；费用归属段不被本动作扩大",
             "check": {"kind": "boundary_scope", "boundary": "preserve_host"},
             "verification": "code"},
        ],
        "model_verification": [],
    },
    "R10-A1": {
        "semantics": {
            "subject": "赎回基金份额的基金份额持有人",
            "action": "承担赎回费用并在赎回时收取，赎回费用全额计入基金财产",
            "condition": "无条件全额计入；删除按比例归入、招募说明书比例与未归入部分用途的旧表述",
            "fee_terms": "不保留也不新增任何费用比例或数字",
            "ownership": "赎回费用全额计入基金财产",
            "allowed_changes": [
                "删除按比例归入基金财产、按招募说明书列示比例、未归入部分用于登记费等旧表述",
                "删除目标范围内与短期持有赎回费绑定的旧句",
            ],
            "must_preserve": [
                "同段目标范围之前的申购费、费用列表、编号等非目标内容逐字保留",
                "同段目标范围之后的文本逐字保留",
            ],
            "forbidden_additions": [
                "不得新增持有期、渠道、投资者类别等条件",
                "不得新增费用比例或数字",
                "不得改变费用承担主体或归属关系",
            ],
            "unsupported": ["跨段目标", "跨 cell 目标", "结构屏障", "同段内无法唯一确定费用归属范围"],
        },
        "locate": {
            "mode": "model_assisted",
            "instruction": (
                "在给定的单个段落中定位唯一的、完整的旧赎回费用承担与归入基金财产条款范围。"
                "范围必须以“赎回费用由”开头，覆盖该费用承担、收取时点、归入基金财产比例或全额表述，"
                "直至相应句号结束；如果该段落还把短期持有赎回费句并入同一归属条款，也一并纳入范围。"
                "不得包含申购费、认购费、赎回费率表、编号或与赎回费用归属无关的句子。"
                "quote 必须是段落中的逐字连续原文，不允许省略、改写或拼接；找不到时返回空 quote。"
            ),
            "start_prefixes": ["赎回费用由"],
            "forbid_contains": ["申购费", "认购费", "管理费", "托管费", "销售服务费"],
            "require_end": ["。", "；"],
            "min_chars": 20,
            "max_chars": 500,
            "prefilter": {"all": ["赎回费用"], "any": ["承担", "归入基金财产", "计入基金财产"]},
            "max_locate_paragraphs": 3,
        },
        "generation": {
            "mode": "generate",
            "kind": "redemption_fee_ownership",
            "instruction": (
                "根据 RULE_REQUIREMENTS 与 CONTRACT_SOURCE，写出替换后的赎回费用承担与归属条款正文。"
                "只保留持有人承担、赎回时收取、全额计入基金财产；删除按比例归入、招募说明书、登记费及"
                "短期持有条件相关旧表述；不得新增条件、渠道、类别或数字。"
                "replacement_text 仅为替换范围的新正文，不包含替换范围之外的文字。source_quote 必须逐字等于 CONTRACT_SOURCE 内容；changes[].basis_requirement 只能使用 RULE_REQUIREMENTS 中列出的 id，或不提供该字段。"
            ),
            "reference_text": (
                "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。"
                "赎回费用全额计入基金财产。"
            ),
            "max_chars": 200,
        },
        "requirements": [
            {"id": "R10-REQ-1", "kind": "must_state",
             "text": "赎回费用由赎回基金份额的基金份额持有人承担",
             "check": {"kind": "contains_all", "values": ["赎回费用由赎回基金份额的基金份额持有人承担"]},
             "verification": "code"},
            {"id": "R10-REQ-2", "kind": "must_state",
             "text": "在基金份额持有人赎回基金份额时收取",
             "check": {"kind": "contains_all", "values": ["在基金份额持有人赎回基金份额时收取"]},
             "verification": "code"},
            {"id": "R10-REQ-3", "kind": "must_state",
             "text": "赎回费用全额计入基金财产",
             "check": {"kind": "contains_all", "values": ["全额计入基金财产"]},
             "verification": "code+model"},
            {"id": "R10-REQ-4", "kind": "must_not_state",
             "text": "不得保留按比例归入、招募说明书比例或未归入部分用途的旧表述",
             "check": {"kind": "not_contains", "values": ["未归入基金财产", "登记费", "招募说明书", "比例"]},
             "verification": "code"},
            {"id": "R10-REQ-5", "kind": "must_not_state",
             "text": "不得新增条件、渠道或数字",
             "check": {"kind": "no_digits_and_no_conditions",
                       "conditions": ["超过一年", "少于", "不足", "持有期", "直销", "渠道", "特定"]},
             "verification": "code"},
            {"id": "R10-REQ-6", "kind": "must_preserve",
             "text": "费用承担主体、收取时点与全额归属与规则要求一致，未改变归属关系或加入未授权条件",
             "check": {"kind": "semantic_review"},
             "verification": "model"},
        ],
        "model_verification": ["R10-REQ-3", "R10-REQ-6"],
    },
}

ACTION_ORDER = ["R01-A1", "R02-A1", "R03-A3", "R04-A1", "R11-A1", "R10-A1"]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build() -> dict:
    v1_raw = V1_PATH.read_bytes()
    v1 = json.loads(v1_raw)
    by_id = {action["action_id"]: action for action in v1["actions"]}
    templates = v1["templates"]
    actions = []
    for action_id in ACTION_ORDER:
        base = by_id[action_id]
        contract = CONTRACTS[action_id]
        template = templates[base["template_id"]]
        actions.append({
            "rule_id": base["rule_id"],
            "action_id": action_id,
            "description": base["description"],
            "section_anchor": base["section_anchor"],
            "section_aliases": list(base.get("section_aliases", [])),
            "subsection_anchor": base["subsection_anchor"],
            "subsection_aliases": list(base.get("subsection_aliases", [])),
            "regions": list(base["regions"]),
            "scope": base["scope"],
            "operation": base["operation"],
            "requires_profile": list(base.get("requires_profile", [])),
            "condition": base["condition"],
            "approval": {"auto_write": False, "approved": False, "status": "unreleased"},
            "semantics": contract["semantics"],
            "locate": contract["locate"],
            "generation": contract["generation"],
            "requirements": contract["requirements"],
            "model_verification": contract["model_verification"],
            "source_provenance": {
                "v1_rule_source": "rules/rules_v1.json",
                "v1_rules_sha256": _sha256_bytes(v1_raw),
                "template_source_paragraph": template.get("source_paragraph"),
                "template_source_provenance": template.get("source_provenance", []),
                "old_texts": list(base.get("old_texts", base.get("old_triggers", []))),
            },
        })
    return {
        "version": "v2",
        "schema_version": "2",
        "compiled_at": "2026-10-13",
        "source": {
            "description": "由 v1 来源指引整理的可执行语义契约；模板仅作参考文案，不再要求生成文字逐字相等",
            "v1_rules_sha256": _sha256_bytes(v1_raw),
            "design_doc": "docs/AI_EDITING_DESIGN.md",
        },
        "release_policy": {
            "status": "unreleased",
            "basis": "v2 语义契约尚未完成独立样本质量门槛与离线发布批准；真实运行为隔离评测模式，不构成发布",
            "auto_write_enabled": False,
        },
        "actions": actions,
    }


def main() -> None:
    package = build()
    V2_PATH.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = _sha256_bytes(V2_PATH.read_bytes())
    print(json.dumps({"path": str(V2_PATH), "sha256": digest, "actions": [a["action_id"] for a in package["actions"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
