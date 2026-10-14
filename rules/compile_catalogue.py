"""Compile reviewed wording from the correction guide; never grants release approval."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx"

def compile_catalogue():
    raw = (ROOT / SOURCE).read_bytes()
    with ZipFile(ROOT / SOURCE) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = {i: "".join(t.text or "" for t in p.findall(".//w:t", ns))
                  for i, p in enumerate(document.findall("w:body/w:p", ns), 1)}
    def after(n, marker): return paragraphs[n].split(marker, 1)[1]
    def quoted(n):
        import re
        return re.findall("“([^”]+)”", paragraphs[n])
    def provenance(numbers):
        return [{"paragraph": n, "sha256": hashlib.sha256(paragraphs[n].encode()).hexdigest()}
                for n in numbers]
    templates, actions = {}, []
    action_metrics = {"location_precision": {"min": 0.99}, "location_recall": {"min": 0.95},
                      "unsafe_edits": {"max": 0}, "template_exactness": {"min": 1.0},
                      "positive_cases": {"min": 30}, "negative_cases": {"min": 30},
                      "independent_cases": {"min": 10}, "body_support_cases": {"min": 10},
                      "summary_support_cases": {"min": 10}, "structure_support_cases": {"min": 10}}
    profile_metrics = {"accuracy": {"min": 0.99}, "precision": {"min": 0.99},
                       "recall": {"min": 0.95}, "positive_cases": {"min": 30},
                       "negative_cases": {"min": 30}, "independent_cases": {"min": 10}}
    anchors = {
        "definition": ("释义", "基金份额类别"),
        "classes": ("基金的基本情况", "份额类别"),
        "trade": ("基金份额的申购与赎回", "申购和赎回的价格、费用及其用途"),
        "service": ("基金费用与税收", "基金销售服务费"),
        "income": ("基金的收益与分配", "收益分配"),
        "liquidation": ("基金合同的变更、终止与基金财产的清算", "基金财产清算剩余资产的分配"),
    }
    profiles = {
        "always": [], "single_class": ["share_classes"], "multi_class": ["share_classes"],
        "has_service_fee": ["sales_service_fee_by_class"], "no_service_fee": ["sales_service_fee_by_class"],
        "fee_groups": ["share_classes", "subscription_fee_by_class", "sales_service_fee_by_class"],
        "floating_single": ["share_classes", "floating_management_fee"],
        "floating_multi": ["share_classes", "floating_management_fee"],
        "nonfloating_service_multi": ["share_classes", "floating_management_fee", "sales_service_fee_by_class"],
    }
    def add(rule, suffix, area, scope, operation, condition, old, new, source, description):
        aid = f"R{rule:02d}-A{suffix}"
        slots = {token: group for token, group in [("A类基金份额", "subscription_group"),
                ("C类基金份额", "service_group")] if token in new or any(token in t for t in old)}
        templates[aid] = {"text": new, "source_paragraph": source[0],
                          "source_provenance": provenance(source), "template_slots": slots}
        section, subsection = anchors[area]
        required = list(profiles[condition])
        if slots:
            for field in profiles["fee_groups"]:
                if field not in required: required.append(field)
        actions.append({"rule_id": f"R{rule:02d}", "action_id": aid, "description": description,
            "section_anchor": section, "subsection_anchor": subsection, "regions": ["body", "summary"],
            "scope": scope, "old_triggers": old, "old_texts": old, "new_triggers": [new] if new else [],
            "operation": operation, "template_id": aid, "order": len(actions) + 1,
            "risk_class": "high", "requires_profile": required, "condition": condition,
            "on_unknown": "failed", "auto_write": False,
            "release_threshold": {"registration_id": "fundlex-conservative-gates-2026-10-13-v1",
                                  "registered_before_full_evaluation": True,
                                  "metrics": action_metrics,
                                  "profile_metrics": {field: profile_metrics for field in required}},
            "evaluation_metrics": None, "evaluation_report_id": None, "approval_record": None,
            "approved": False,
            "source_provenance": provenance(source), "template_slots": slots})
        actions[-1]['recognition_kind'] = 'literal'
        if area == 'classes':
            actions[-1]['subsection_aliases'] = ['份额类别设置','基金份额类别设置','基金份额类别',
                '基金份额的类别','基金份额分类','基金份额的分类','基金份额的类别设置',
                '基金的份额类别设置','基金的份额类别','基金份额类别的设置']
        if area == 'trade':
            actions[-1]['section_aliases'] = ['基金份额的申购和赎回','基金份额的申购、赎回与转换']
            actions[-1]['subsection_aliases'] = ['申购与赎回的价格、费用及其用途','申购和赎回的费用及其用途',
                '申购与赎回的费用及其用途']
    add(1,1,"definition","paragraph","append","fee_groups",[paragraphs[3]],paragraphs[5],[3,5,7,8,9],"份额类别定义追加直销及持续持有费用规则")
    add(2,1,"classes","paragraph","append","fee_groups",[after(12,"：")],after(13,"："),[12,13,15,16,17],"份额类别设置追加费用规则")
    add(3,1,"classes","phrase","replace","has_service_fee",["调低赎回费率"],"调低销售服务费率",[20,22],"有销售服务费时替换可调低费率")
    add(3,2,"classes","phrase","delete","no_service_fee",["、调低赎回费率"],"",[20,22],"无销售服务费时删除可调低赎回费率")
    add(3,3,"classes","phrase","delete","always",["并报中国证监会备案"],"",[20,23],"删除备案语句")
    add(4,1,"classes","sentence","delete","multi_class",[after(25,"：")],"",[25,26],"删除类别不得互相转换完整原句")
    add(5,1,"trade","sentence","replace","single_class",[quoted(32)[0]],quoted(32)[1],[29,32],"单类别申购费率及直销豁免")
    add(6,1,"trade","sentence","replace","multi_class",[quoted(34)[0]],quoted(34)[1],[29,34,35],"多类别申购费率及直销豁免")
    add(7,1,"trade","sentence","replace","multi_class",[quoted(41)[0]],quoted(41)[1],[37,41],"多类别赎回金额扣除或加上费用")
    add(8,1,"trade","sentence","replace","single_class",[after(44,"：")],after(45,"："),[44,45],"单类别申购费用承担及直销豁免")
    add(9,1,"trade","paragraph","replace","multi_class",[after(47,"："),after(48,"：")],after(49,"："),[47,48,49],"多类别申购费用承担及直销豁免")
    add(10,1,"trade","paragraph","replace","always",[after(52,"："),after(53,"：")],after(54,"："),[52,53,54],"赎回费全额计入基金财产")
    add(11,1,"trade","sentence","delete","always",[quoted(57)[0]],"",[56,57],"删除旧短期持有赎回费句")
    promo = [quoted(n)[0] for n in [61,62,63]]
    add(12,1,"trade","sentence","replace","single_class",promo,quoted(65)[1],[61,62,63,65],"单类别促销可调低申购费率")
    add(13,1,"trade","sentence","replace","multi_class",promo,quoted(67)[1],[61,62,63,67],"多类别促销可调低申购及销售服务费率")
    add(14,1,"service","paragraph","replace","multi_class",[paragraphs[77]],"\n".join(paragraphs[n] for n in range(79,86)),[74,77] + list(range(79,86)),"替换旧销售服务费支付段落为直销返还及其他销售机构费用支付规则")
    add(15,1,"service","paragraph","delete","multi_class",[paragraphs[88]],"",[88,90],"删除销售服务费用途段落")
    add(15,2,"service","paragraph","delete","multi_class",[paragraphs[89]],"",[89,90],"删除销售服务费使用范围段落")
    add(16,1,"income","phrase","replace","multi_class",[quoted(93)[0]],quoted(93)[1],[92,93],"收益分配按类别费用收取不同调整")
    floating_old = [after(n,"：") for n in [96,97]]
    add(17,1,"liquidation","paragraph","replace","floating_single",floating_old,after(99,"："),[96,97,99],"浮动管理费单类别清算费用调整")
    add(17,2,"liquidation","paragraph","replace","floating_multi",floating_old,paragraphs[101],[96,97,101],"浮动管理费多类别清算费用调整")
    add(17,3,"liquidation","paragraph","replace","nonfloating_service_multi",[after(103,"：")],after(106,"："),[102,103,105,106],"非浮动管理费多类别销售服务费返还")
    for action in actions:
        if action['rule_id'] == 'R04':
            action['recognition_kind'] = 'conversion_prohibition'
        if action['rule_id'] == 'R11':
            action['recognition_kind'] = 'short_holding_redemption'
            action['host_policy'] = 'fee_rate_or_adjustment'
    return {"version": "v1", "schema_version": "1", "source": SOURCE,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_paragraph_count": len(paragraphs),
        "release_policy": {"status": "unreleased", "basis": "逐 action 画像、候选、结构、真实模型和独立样本门槛尚未完成；无批准记录",
                           "evaluation_report_id": None, "approval_record": None},
        "template_instantiation": {"mode": "fixed_literal_only", "unknown": "failed", "concrete_variants_approved": False,
            "slots": {"A类基金份额": "subscription_group", "C类基金份额": "service_group"},
            "source_provenance": provenance([7,8,9,15,16,17,35])},
        "no_change_branches": [{"source_paragraph": 40, "condition": "single_class", "rule_id": "R07"},
                               {"source_paragraph": 105, "condition": "single_class", "rule_id": "R17"}],
        "templates": templates, "actions": actions}

if __name__ == "__main__":
    (ROOT / "rules/rules_v1.json").write_text(json.dumps(compile_catalogue(), ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8", newline="\n")
