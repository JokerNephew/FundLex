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

ACTION_ORDER = ["R01-A1", "R02-A1", "R03-A3", "R04-A1", "R11-A1", "R10-A1",
                "R03-A1", "R03-A2", "R05-A1", "R06-A1", "R07-A1", "R08-A1", "R09-A1",
                "R12-A1", "R13-A1", "R14-A1", "R15-A1", "R15-A2", "R16-A1",
                "R17-A1", "R17-A2", "R17-A3"]


def _template_requirements(action_id: str, contains: list[str], forbid: list[str] | None = None) -> list[dict]:
    requirements = [{"id": f"{action_id}-REQ-1", "kind": "must_preserve",
                     "text": "改写内容必须与规则指引文案逐字一致（类别槽位按当前合同实际类别实例化）",
                     "check": {"kind": "template_exact"}, "verification": "code"},
                    {"id": f"{action_id}-REQ-2", "kind": "must_state",
                     "text": "改写后必须包含规则要求的关键表述",
                     "check": {"kind": "contains_all", "values": contains}, "verification": "code"}]
    if forbid:
        requirements.append({"id": f"{action_id}-REQ-3", "kind": "must_not_state",
                             "text": "改写后不得保留旧的费用对象或条件表述",
                             "check": {"kind": "not_contains", "values": forbid}, "verification": "code"})
    return requirements


def _delete_requirements(action_id: str) -> list[dict]:
    return [{"id": f"{action_id}-REQ-1", "kind": "must_not_state",
             "text": "目标内容已删除，范围之外文字保持不变",
             "check": {"kind": "delete_only"}, "verification": "code"},
            {"id": f"{action_id}-REQ-2", "kind": "must_preserve",
             "text": "只删除目标内容；同段/相邻文字与其他区域逐字保留",
             "check": {"kind": "boundary_scope", "boundary": "preserve_outside"}, "verification": "code"}]


# The remaining catalogue actions. Their replacement text is the published rule
# literal (or a deletion), so it is assembled and verified by code with class
# slots instantiated from the current contract evidence - the model never
# invents policy text for them.
CONTRACTS.update({
    "R03-A1": {
        "semantics": {
            "subject": "费率调整条款中的“调低赎回费率”表述",
            "action": "将“调低赎回费率”替换为“调低销售服务费率”",
            "condition": "仅当合同存在收取销售服务费的类别（has_service_fee）时适用",
            "fee_terms": "不新增任何费率数字；只改变可调低费用的对象",
            "ownership": None,
            "allowed_changes": ["把“调低赎回费率”替换为“调低销售服务费率”"],
            "must_preserve": ["同句其余可调费用表述、数字与编号", "其他区域、目录、部件"],
            "forbidden_additions": ["不得新增费率数字、比例或条件"],
            "unsupported": ["无销售服务费证据", "目标短语不在费率调整句", "跨段/屏障/无法唯一定位"],
        },
        "locate": {"mode": "code_literal", "triggers": ["调低赎回费率"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R03-A1", ["调低销售服务费率"], ["调低赎回费率"]),
        "model_verification": [],
    },
    "R03-A2": {
        "semantics": {
            "subject": "费率调整条款中的“、调低赎回费率”",
            "action": "删除该短语，保留同句其他可调费用表述",
            "condition": "合同没有销售服务费类别（no_service_fee）时适用",
            "fee_terms": "不改变其他费率数字与表述",
            "ownership": None,
            "allowed_changes": ["删除“、调低赎回费率”"],
            "must_preserve": ["同句其他可调费用表述与数字", "其他区域与部件"],
            "forbidden_additions": ["不得新增任何文字"],
            "unsupported": ["存在销售服务费证据", "目标短语不存在", "跨段/屏障/无法唯一定位"],
        },
        "locate": {"mode": "code_literal", "triggers": ["、调低赎回费率"]},
        "generation": {"mode": "delete"},
        "requirements": _delete_requirements("R03-A2"),
        "model_verification": [],
    },
    "R05-A1": {
        "semantics": {
            "subject": "单一类别基金的申购费率条款",
            "action": "替换为含直销机构豁免的申购费率条款",
            "condition": "单一类别（single_class）时适用",
            "fee_terms": "不新增具体费率；保留“由基金管理人决定并在招募说明书列示”",
            "ownership": None,
            "allowed_changes": ["整句替换为规则指引文案"],
            "must_preserve": ["费率决定与列示方式", "非目标区域与部件"],
            "forbidden_additions": ["不得新增费率数字或条件"],
            "unsupported": ["多类别合同", "目标句不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal", "triggers": ["本基金的申购费率由基金管理人决定，并在招募说明书中列示。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R05-A1", ["通过直销机构申购本基金不收取申购费"]),
        "model_verification": [],
    },
    "R06-A1": {
        "semantics": {
            "subject": "多类别基金的申购费率条款",
            "action": "按当前合同实际类别替换为含类别费用归属与直销豁免的条款",
            "condition": "多类别（multi_class）且类别收费分组可核验时适用",
            "fee_terms": "不新增费率数字；类别名称只来自当前合同",
            "ownership": None,
            "allowed_changes": ["整句替换为规则指引文案", "类别槽位按实际申购费组/销售服务费组实例化"],
            "must_preserve": ["费率决定与列示方式", "非目标区域与部件"],
            "forbidden_additions": ["不得新增费率数字或条件", "不得使用合同之外的类别名称"],
            "unsupported": ["单类别合同", "类别收费分组不完整", "目标句不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal", "triggers": ["本基金的申购费率由基金管理人决定，并在招募说明书中列示。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R06-A1", ["通过直销机构申购本基金", "不收取申购费"]),
        "model_verification": [],
    },
    "R07-A1": {
        "semantics": {
            "subject": "多类别基金的赎回金额计算条款",
            "action": "替换为“按当日该类基金份额净值并扣除或加上相应费用”的表述",
            "condition": "多类别（multi_class）时适用",
            "fee_terms": "不新增费率或数字",
            "ownership": None,
            "allowed_changes": ["整句替换为规则指引文案"],
            "must_preserve": ["金额单位与其他计算要素", "非目标区域与部件"],
            "forbidden_additions": ["不得新增数字或条件"],
            "unsupported": ["单类别合同", "目标句不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal",
                   "triggers": ["赎回金额为按实际确认的有效赎回份额乘以当日对应份额类别的基金份额净值并扣除相应的费用，赎回金额单位为元。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R07-A1", ["并扣除或加上相应的费用"]),
        "model_verification": [],
    },
    "R08-A1": {
        "semantics": {
            "subject": "单一类别基金的申购费用承担条款",
            "action": "替换为含直销豁免与费用承担的条款",
            "condition": "单一类别（single_class）时适用",
            "fee_terms": "不新增费率数字",
            "ownership": "申购费用由投资人承担、不列入基金财产（保留）",
            "allowed_changes": ["整句替换为规则指引文案"],
            "must_preserve": ["费用承担与不列入基金财产的归属关系", "非目标区域与部件"],
            "forbidden_additions": ["不得新增数字或条件"],
            "unsupported": ["多类别合同", "目标句不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal", "triggers": ["申购费用由投资人承担，不列入基金财产。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R08-A1", ["通过直销机构申购本基金不收取申购费", "不列入基金财产"]),
        "model_verification": [],
    },
    "R09-A1": {
        "semantics": {
            "subject": "多类别基金的申购费用承担段落",
            "action": "整段替换为含实际类别费用归属与直销豁免的段落",
            "condition": "多类别（multi_class）且类别收费分组可核验时适用",
            "fee_terms": "不新增费率数字；类别名称只来自当前合同",
            "ownership": "申购费组类别的申购费用由投资人承担、不列入基金财产；服务费组类别不收取申购费用",
            "allowed_changes": ["整段替换为规则指引文案", "类别槽位按实际类别分组实例化"],
            "must_preserve": ["费用归属关系", "非目标区域与部件"],
            "forbidden_additions": ["不得新增数字或条件", "不得使用合同之外的类别名称"],
            "unsupported": ["单类别合同", "类别收费分组不完整", "整段与指引旧文不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal", "triggers": ["本基金A类基金份额的申购费用由投资人承担，不列入基金财产；C类基金份额不收取申购费用。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R09-A1", ["通过直销机构申购本基金", "不列入基金财产"]),
        "model_verification": [],
    },
    "R12-A1": {
        "semantics": {
            "subject": "单一类别基金的促销费率调整句",
            "action": "替换为仅可调低申购费率的表述",
            "condition": "单一类别（single_class）时适用",
            "fee_terms": "不新增费率数字",
            "ownership": None,
            "allowed_changes": ["整句替换为规则指引文案"],
            "must_preserve": ["同段其他费率调整表述", "非目标区域与部件"],
            "forbidden_additions": ["不得新增赎回费率或转换费率表述"],
            "unsupported": ["多类别合同", "目标句不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal",
                   "triggers": ["基金管理人可以适当调低基金申购费率和赎回费率。",
                                "基金管理人可以适当调低基金申购费率、赎回费率和转换费率。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R12-A1", ["适当调低基金申购费率"], ["赎回费率"]),
        "model_verification": [],
    },
    "R13-A1": {
        "semantics": {
            "subject": "多类别基金的促销费率调整句",
            "action": "替换为可调低申购费率与销售服务费率的表述",
            "condition": "多类别（multi_class）时适用",
            "fee_terms": "不新增费率数字",
            "ownership": None,
            "allowed_changes": ["整句替换为规则指引文案"],
            "must_preserve": ["同段其他费率调整表述", "非目标区域与部件"],
            "forbidden_additions": ["不得新增赎回费率或转换费率表述"],
            "unsupported": ["单类别合同", "目标句不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal",
                   "triggers": ["基金管理人可以适当调低基金申购费率和赎回费率。",
                                "基金管理人可以适当调低基金申购费率、赎回费率和转换费率。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R13-A1", ["适当调低基金申购费率和销售服务费率"], ["赎回费率"]),
        "model_verification": [],
    },
    "R14-A1": {
        "semantics": {
            "subject": "销售服务费支付段落",
            "action": "整段替换为直销机构返还与其他销售机构支付规则（按实际销售服务费类别实例化）",
            "condition": "多类别且存在销售服务费类别时适用",
            "fee_terms": "保留每日计提、按月支付与“超过一年”期限表述；不新增数字",
            "ownership": "直销机构计提部分在赎回或合同终止时返还投资者；其他销售机构按持有期支付",
            "allowed_changes": ["整段替换为规则指引文案", "类别槽位按实际销售服务费类别实例化"],
            "must_preserve": ["费用归属与支付方式的关键条件", "非目标区域与部件"],
            "forbidden_additions": ["不得新增费率数字或条件", "不得使用合同之外的类别名称"],
            "unsupported": ["无销售服务费类别", "整段与指引旧文不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal",
                   "triggers": ["C类基金份额的销售服务费每日计提，按月支付。由基金管理人向基金托管人发送基金销售服务费划付指令，经基金托管人复核后于次月首日起10个工作日内从基金财产中一次性支付给登记机构，由登记机构代付给销售机构。若遇法定节假日、公休日等，支付日期顺延。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R14-A1", ["直销机构", "销售服务费每日计提", "随赎回款"]),
        "model_verification": [],
    },
    "R15-A1": {
        "semantics": {
            "subject": "销售服务费用途段落",
            "action": "整段删除",
            "condition": "多类别且存在销售服务费类别时适用",
            "fee_terms": None,
            "ownership": None,
            "allowed_changes": ["删除该段落"],
            "must_preserve": ["其他费用段落与全文其余部分", "非目标区域与部件"],
            "forbidden_additions": ["不得新增任何文字"],
            "unsupported": ["无销售服务费类别", "整段与指引旧文不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal",
                   "triggers": ["C类基金份额的销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。"]},
        "generation": {"mode": "delete"},
        "requirements": _delete_requirements("R15-A1"),
        "model_verification": [],
    },
    "R15-A2": {
        "semantics": {
            "subject": "销售服务费使用范围段落",
            "action": "整段删除",
            "condition": "多类别且存在销售服务费类别时适用",
            "fee_terms": None,
            "ownership": None,
            "allowed_changes": ["删除该段落"],
            "must_preserve": ["其他费用段落与全文其余部分", "非目标区域与部件"],
            "forbidden_additions": ["不得新增任何文字"],
            "unsupported": ["无销售服务费类别", "整段与指引旧文不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal",
                   "triggers": ["C类基金份额的销售服务费使用范围不包括基金募集期间的上述费用。"]},
        "generation": {"mode": "delete"},
        "requirements": _delete_requirements("R15-A2"),
        "model_verification": [],
    },
    "R16-A1": {
        "semantics": {
            "subject": "收益分配说明中的类别费用差异表述",
            "action": "替换为“按类别费用收取不同”的表述",
            "condition": "多类别（multi_class）且类别收费分组可核验时适用",
            "fee_terms": "不新增费率数字",
            "ownership": None,
            "allowed_changes": ["替换“不收取销售服务费，而……收取销售服务费”为“费用收取不同”"],
            "must_preserve": ["同句其他收益分配表述", "非目标区域与部件"],
            "forbidden_additions": ["不得新增数字或条件", "不得使用合同之外的类别名称"],
            "unsupported": ["单类别合同", "类别收费分组不完整", "目标短语不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal",
                   "triggers": ["由于本基金A类基金份额不收取销售服务费，而C类基金份额收取销售服务费"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R16-A1", ["费用收取不同"]),
        "model_verification": [],
    },
    "R17-A1": {
        "semantics": {
            "subject": "浮动管理费单一类别的清算分配段落",
            "action": "替换为含返还或有管理费或扣除超额管理费的清算分配表述",
            "condition": "浮动管理费且单一类别（floating_single）时适用",
            "fee_terms": "不新增费率数字",
            "ownership": "或有管理费返还或超额管理费扣除（保留指引表述）",
            "allowed_changes": ["整段替换为规则指引文案"],
            "must_preserve": ["清算顺序与分配方式", "非目标区域与部件"],
            "forbidden_additions": ["不得新增数字或条件"],
            "unsupported": ["非浮动管理费", "多类别合同", "整段与指引旧文不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal",
                   "triggers": ["依据基金财产清算的分配方案，将基金财产清算后的全部剩余资产扣除基金财产清算费用、交纳所欠税款并清偿基金债务后，按基金份额持有人持有的基金份额比例进行分配，并扣除相应的超额管理费（如涉及）。",
                                "依据基金财产清算的分配方案，将基金财产清算后的全部剩余资产扣除基金财产清算费用、交纳所欠税款并清偿基金债务后，按基金份额持有人持有的基金份额比例进行分配，并加上返还基金份额持有人的或有管理费（如有）或扣除相应的超额管理费（如有）。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R17-A1", ["或有管理费（如有）", "超额管理费（如有）"]),
        "model_verification": [],
    },
    "R17-A2": {
        "semantics": {
            "subject": "浮动管理费多类别的清算分配段落",
            "action": "替换为含返还或有管理费、销售服务费或扣除超额管理费的清算分配表述",
            "condition": "浮动管理费且多类别（floating_multi）时适用",
            "fee_terms": "不新增费率数字",
            "ownership": "或有管理费与销售服务费返还或超额管理费扣除（保留指引表述）",
            "allowed_changes": ["整段替换为规则指引文案"],
            "must_preserve": ["清算顺序与分配方式", "非目标区域与部件"],
            "forbidden_additions": ["不得新增数字或条件"],
            "unsupported": ["非浮动管理费", "单类别合同", "整段与指引旧文不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal",
                   "triggers": ["依据基金财产清算的分配方案，将基金财产清算后的全部剩余资产扣除基金财产清算费用、交纳所欠税款并清偿基金债务后，按基金份额持有人持有的基金份额比例进行分配，并扣除相应的超额管理费（如涉及）。",
                                "依据基金财产清算的分配方案，将基金财产清算后的全部剩余资产扣除基金财产清算费用、交纳所欠税款并清偿基金债务后，按基金份额持有人持有的基金份额比例进行分配，并加上返还基金份额持有人的或有管理费（如有）或扣除相应的超额管理费（如有）。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R17-A2", ["或有管理费（如有）、销售服务费（如有）"]),
        "model_verification": [],
    },
    "R17-A3": {
        "semantics": {
            "subject": "非浮动管理费多类别的清算分配段落",
            "action": "替换为含返还销售服务费的清算分配表述",
            "condition": "非浮动管理费、多类别且存在销售服务费（nonfloating_service_multi）时适用",
            "fee_terms": "不新增费率数字",
            "ownership": "销售服务费返还投资者（保留指引表述）",
            "allowed_changes": ["整段替换为规则指引文案"],
            "must_preserve": ["清算顺序与分配方式", "非目标区域与部件"],
            "forbidden_additions": ["不得新增数字或条件"],
            "unsupported": ["浮动管理费或无销售服务费", "单类别合同", "整段与指引旧文不匹配", "跨段/屏障/不唯一"],
        },
        "locate": {"mode": "code_literal",
                   "triggers": ["依据基金财产清算的分配方案，将基金财产清算后的全部剩余资产扣除基金财产清算费用、交纳所欠税款并清偿基金债务后，按基金份额持有人持有的基金份额比例进行分配。"]},
        "generation": {"mode": "template"},
        "requirements": _template_requirements("R17-A3", ["并加上返还基金份额持有人的销售服务费（如有）"]),
        "model_verification": [],
    },
})


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
        # Triggers and rule text come from the frozen v1 package; the v2 contract
        # adds semantics, checks and (for slot actions) class instantiation.
        locate = dict(contract["locate"])
        # Authored business terms select candidates, never authorize writes.
        # Position and the full policy requirements must still be model-bound.
        variant_terms = {
            "R03-A1": ["赎回费率"], "R03-A2": ["赎回费率"],
            "R03-A3": ["备案"], "R05-A1": ["申购费率"], "R06-A1": ["申购费率"],
            "R07-A1": ["赎回金额"], "R08-A1": ["申购费用"], "R09-A1": ["申购费用"],
            "R12-A1": ["调低", "调整费率"], "R13-A1": ["调低", "调整费率"],
            "R14-A1": ["销售服务费"], "R15-A1": ["销售服务费"], "R15-A2": ["销售服务费"],
            "R16-A1": ["销售服务费"],
            "R17-A1": ["清算", "剩余资产"], "R17-A2": ["清算", "剩余资产"],
            "R17-A3": ["清算", "剩余资产"],
        }
        if action_id in variant_terms:
            locate["variant_fallback"] = {"any": variant_terms[action_id], "max_paragraphs": 8,
                                          "range_mode": "policy_core"}
            business_filters = {
                "R05-A1": (["申购费率"], ["决定", "列示"]),
                "R06-A1": (["申购费率"], ["决定", "列示"]),
                "R12-A1": (["申购费率"], ["调低", "下调", "降低"]),
                "R13-A1": (["申购费率"], ["调低", "下调", "降低"]),
                "R14-A1": (["销售服务费"], ["每日计提", "按月", "划付", "支付给"]),
                "R15-A1": (["销售服务费"], ["主要用于", "佣金", "广告费", "促销活动费"]),
                "R15-A2": (["销售服务费"], ["使用范围", "募集期间", "不包括"]),
                "R16-A1": (["销售服务费"], ["由于", "费用收取", "可供分配利润"]),
            }
            if action_id in business_filters:
                all_terms, any_terms = business_filters[action_id]
                locate["variant_fallback"].update(all=all_terms, any=any_terms)
            quote_filters = {
                "R03-A1": (["赎回费率"], ["调低", "降低"]),
                "R03-A2": (["赎回费率"], ["调低", "降低"]),
                "R03-A3": (["备案"], ["报", "备案"]),
                "R05-A1": (["申购费率"], ["决定", "确定", "列示"]),
                "R06-A1": (["申购费率"], ["决定", "确定", "列示"]),
                "R07-A1": (["赎回金额"], ["净值", "费用", "赎回份额"]),
                "R08-A1": (["申购费用"], ["承担", "负担", "不列入", "不计入"]),
                "R09-A1": (["申购费用"], ["承担", "负担", "不列入", "不计入"]),
                "R12-A1": (["申购费率"], ["调低", "下调", "降低"]),
                "R13-A1": (["申购费率"], ["调低", "下调", "降低"]),
                "R14-A1": (["销售服务费"], ["计提", "支付", "划付"]),
                "R15-A1": (["销售服务费"], ["用于", "佣金", "广告", "促销"]),
                "R15-A2": (["销售服务费"], ["使用范围", "募集期间", "不包括"]),
                "R16-A1": (["基金份额", "销售服务费"], ["由于", "收取", "费用"]),
                "R17-A1": (["基金财产"], ["清算", "剩余资产", "基金债务"]),
                "R17-A2": (["基金财产"], ["清算", "剩余资产", "基金债务"]),
                "R17-A3": (["基金财产"], ["清算", "剩余资产", "基金债务"]),
            }
            quote_all, quote_any = quote_filters[action_id]
            locate["variant_fallback"].update(quote_all=quote_all, quote_any=quote_any)
        if locate.get("mode") == "code_literal":
            locate["triggers"] = list(base.get("old_triggers", []))
            locate["old_texts"] = list(base.get("old_texts", base.get("old_triggers", [])))
            if base.get("template_slots"):
                locate["slots"] = dict(base["template_slots"])
        generation = dict(contract["generation"])
        if generation.get("mode") == "template":
            generation["template_text"] = template["text"]
            generation["max_chars"] = max(len(template["text"]) + 200, 400)
            if base.get("template_slots"):
                generation["slots"] = dict(base["template_slots"])
        section_aliases = list(base.get("section_aliases", []))
        if action_id == "R16-A1":
            section_aliases.extend(name for name in ("基金收益与分配", "基金收益分配")
                                   if name not in section_aliases)
        scope_resolution = {"mode": "model_fallback", "max_sections": 4, "max_range_paragraphs": 16}
        if locate["mode"] == "class_definition":
            scope_resolution["business_candidates"] = {"all": ["基金份额"], "any": ["分为", "类别"]}
        elif locate["mode"] == "model_assisted":
            scope_resolution["business_candidates"] = dict(locate.get("prefilter") or {})
        elif locate["mode"] == "code_recognition":
            scope_resolution["business_candidates"] = {"any": [
                "转换" if locate["recognition_kind"] == "conversion_prohibition" else "持续持有"]}
        actions.append({
            "rule_id": base["rule_id"],
            "action_id": action_id,
            "description": base["description"],
            "section_anchor": base["section_anchor"],
            "section_aliases": section_aliases,
            "subsection_anchor": base["subsection_anchor"],
            "subsection_aliases": list(base.get("subsection_aliases", [])),
            "scope_resolution": scope_resolution,
            "regions": list(base["regions"]),
            "scope": base["scope"],
            "operation": base["operation"],
            "requires_profile": list(base.get("requires_profile", [])),
            "condition": base["condition"],
            "approval": {"auto_write": False, "approved": False, "status": "unreleased"},
            "semantics": contract["semantics"],
            "locate": locate,
            "generation": generation,
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
    V2_PATH.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    digest = _sha256_bytes(V2_PATH.read_bytes())
    print(json.dumps({"path": str(V2_PATH), "sha256": digest, "actions": [a["action_id"] for a in package["actions"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
