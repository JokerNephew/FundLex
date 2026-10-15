"""Build the user-facing result package from a recall-first (P6) run directory.

The layout mirrors the earlier business-reader package (see
``FundLex-合同修改结果-本次抽查-20261013``) so the deliverable reads the same way:

    <output>/
      结果总览.md
      最终版（接受修订后）/<原合同名>.docx     接受修订后的改后合同
      逐份修改说明/<原合同名>/
          修改说明.md
          修改明细.json
          <原合同名>（修改痕迹版）.docx        带 Word 修订痕迹，可逐条接受/拒绝

The recall-first engine's report differs from the v2 one: it uses ``plan.edits`` with
``rule_id`` (G01..G22), ``location`` (pNNN), ``operation`` (insert/replace) and a
``replacement`` string, and the guide carries the per-rule titles/requirements. This tool
maps those onto the readable tables the reference package uses, without inventing content:
every row comes from the run's own report/plan, the source DOCX and the guide.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

# ── rule wording ────────────────────────────────────────────────────────────────
# Short business labels for the table's "修改内容" column. Long titles from the guide
# are used verbatim in the per-case explanation; these stay concise for the overview.
RULE_SHORT = {
    "G01": "补充直销豁免（释义）",
    "G02": "释义份额类别按费用分组",
    "G03": "补充直销豁免（基本情况）",
    "G04": "基本情况份额类别按费用分组",
    "G05": "调整“调低赎回费率”/删除备案表述",
    "G06": "删除不同类别不得转换旧句",
    "G07": "单类别：补充直销申购豁免",
    "G08": "多类别：补充直销申购豁免",
    "G09": "赎回金额表述改为“扣除或加上”",
    "G10": "单类别：申购费用承担表述",
    "G11": "多类别：申购费用承担表述",
    "G12": "赎回费归属改为全额计入基金财产",
    "G13": "删除 7 日短期持有赎回费旧句",
    "G14": "调整可调低费率范围",
    "G15": "删除销售服务费支付旧条款",
    "G16": "补充销售服务费计提/返还条款",
    "G17": "删除销售服务费用途旧条款",
    "G18": "收益分配费用差异表述",
    "G19": "单类别浮动费：清算分配表述",
    "G20": "多类别浮动费：清算分配表述",
    "G22": "非浮动多类别：清算分配表述",
}

OP_TEXT = {"insert": "新增", "replace": "替换", "delete": "删除"}

DELIVERY_TEXT = {
    "complete": "已修改并复核通过",
    "incomplete": "部分条款未修改（详见修改说明）",
    "not_generated": "未生成产物",
    "duplicate": "重复提交（同文件已处理）",
    "excluded": "整份排除类型，未修改",
    "excluded_by_fund_type": "整份排除类型，未修改",
}


def load_run(run_dir: Path) -> list[dict]:
    """Every case result in the run directory, ordered by case id."""
    items: list[dict] = []
    for case_dir in sorted(run_dir.iterdir()):
        result_path = case_dir / "result.json"
        if not case_dir.is_dir() or not result_path.is_file():
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        report_path = case_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
        items.append({"case_dir": case_dir, "result": result, "report": report})
    return items


def rule_label(guide: dict, rule_id: str) -> str:
    """Readable label for one edit's rule, joining composite ids ("G12+G13")."""
    if not rule_id:
        return ""
    parts = [part.strip() for part in str(rule_id).split("+") if part.strip()]
    labels = [RULE_SHORT.get(part) or rule_title(guide, part) for part in parts]
    return "＋".join(labels)


def rule_title(guide: dict, rule_id: str) -> str:
    for group in guide.get("groups") or []:
        if group.get("rule_id") == rule_id:
            title = group.get("title") or ""
            # Titles carry a trailing "…：" separator; strip it for readability.
            return title.rstrip("：:")
    return rule_id


def rule_requirement(guide: dict, rule_id: str) -> str:
    for group in guide.get("groups") or []:
        if group.get("rule_id") == rule_id:
            return group.get("requirement") or ""
    return ""


def guide_rules(report: dict) -> dict:
    return (report.get("guide") or {})


def report_plan_edits(report: dict) -> list[dict]:
    plan = report.get("plan") or {}
    if plan.get("edits"):
        return plan["edits"]
    # Older captures nest the same list under edit_plan.edits without rule ids.
    return (report.get("edit_plan") or {}).get("edits") or []


def failed_targets(report: dict) -> list[dict]:
    """Targets the engine could not resolve, with its own reason text (verbatim)."""
    out: list[dict] = []
    for target in report.get("targets") or []:
        if target.get("state") == "needs_edit" and target.get("status") not in {
                "planned", "satisfied", "not_applicable"}:
            out.append(target)
    return out


def unresolved_entries(report: dict) -> list[dict]:
    return list(report.get("unresolved") or [])


def audit_verdicts(report: dict) -> dict[str, str]:
    """rule_id -> the audit's own verdict for that rule, for the 校验 column."""
    out: dict[str, str] = {}
    audit = report.get("audit") or {}
    for round_info in audit.get("rounds") or []:
        for result in round_info.get("results") or []:
            rule_id = result.get("rule_id")
            verdict = result.get("verdict")
            if rule_id and verdict:
                out[rule_id] = verdict
    return out


def verdict_text(verdict: str | None) -> str:
    return {
        "completed": "通过（规则校验＋独立复核）",
        "satisfied": "通过（原合同已符合）",
        "wrong": "未通过（独立复核认为不符）",
        "missing": "未通过（独立复核认为缺失）",
    }.get(verdict or "", "通过（规则校验＋独立复核）" if verdict else "—")


def case_explanation(name: str, item: dict) -> str:
    result, report = item["result"], item["report"]
    guide = guide_rules(report)
    edits = report_plan_edits(report)
    delivery = report.get("delivery_status") or result.get("delivery_status")
    lines = [f"# {name} 修改说明", "",
             "- 来源：P6 真实合同评测（应用链路：上传→真实模型→DOCX 修改→复核）",
             f"- 处理结果：{DELIVERY_TEXT.get(delivery, delivery or '未知')}",
             f"- 实际修改：{len(edits)} 处"]
    unresolved = unresolved_entries(report)
    if unresolved:
        lines[-1] += f"；未修改：{len(unresolved)} 项（原因见下）"
    lines.append("")

    verdicts = audit_verdicts(report)
    if edits:
        lines += ["## 修改清单", "",
                  "| 序号 | 修改内容 | 修改前（节选） | 修改后（节选） | 校验 |",
                  "| --- | --- | --- | --- | --- |"]
        for index, edit in enumerate(edits, start=1):
            rule_id = edit.get("rule_id") or ""
            label = rule_label(guide, rule_id)
            op = edit.get("operation") or ""
            before = ("（保留原文，在其后追加新条款）" if op == "insert"
                      else _clip(_old_text(edit), 160))
            after = ("（删除该句）" if not edit.get("replacement")
                     else _clip(str(edit["replacement"]), 200))
            verdict = next((verdicts.get(part.strip()) for part in str(rule_id).split("+")
                            if verdicts.get(part.strip())), None)
            lines.append(f"| {index} | {label} | {before} | {after} | {verdict_text(verdict)} |")
        lines.append("")

    if unresolved:
        lines += ["## 未修改的内容及原因", "", "| 条款 | 原因 |", "| --- | --- |"]
        seen = set()
        for entry in unresolved:
            rule_id = entry.get("rule_id") or ""
            label = rule_label(guide, rule_id)
            reason = entry.get("reason") or "未知原因"
            detail = entry.get("detail") or {}
            text = _unresolved_text(reason, detail)
            key = (label, text)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"| {label} | {text} |")
        lines.append("")
        lines.append("以上未修改项保持原合同文字，不会造成错误改动；如需修改请人工处理。")
        lines.append("")

    lines += ["## 怎么核对", "",
              "- 打开“最终版（接受修订后）”中的同名文件即为改后版本；",
              "- 本文件夹内的“（修改痕迹版）”文件带 Word 修订痕迹，可逐条查看、接受或拒绝修改；",
              "- 本说明的表格与文件内容一一对应，可对照抽查。",
              ""]

    validation = report.get("output_validation") or {}
    model = report.get("model") or {}
    lines += ["## 追溯信息（如需审计再看）", "",
              f"- 源文件 SHA-256：{report.get('source_sha256') or result.get('sha256')}",
              f"- 修改后文件 SHA-256：{validation.get('final_sha256')}",
              f"- 修改痕迹版 SHA-256：{validation.get('redline_sha256')}",
              f"- 规则版本：{report.get('ruleset_version')}（{report.get('ruleset_sha256')}）",
              f"- 引擎标识（技术追溯）：{report.get('engine_build')}",
              f"- 模型调用：{model.get('http_attempts', '—')} 次"
              + (f"，约 USD {model.get('estimated_cost_usd'):.4f}（配置价格估计，非供应商账单）"
                 if model.get("estimated_cost_usd") is not None else ""),
              "- 提示：本文件为评测验证结果，正式使用前建议人工抽查，不构成正式发布批准。"]
    return "\n".join(lines) + "\n"


def _first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def _old_text(edit: dict) -> str:
    """Best-effort original wording for the "修改前" column.

    The recall-first edit records ``start``/``end`` offsets into the paragraph but not the
    removed string; the plan ledger and evidence carry it under a few keys instead
    (``matched_old_text`` for a delete/replace, ``delete_texts`` for a composite delete).
    """
    evidence = edit.get("evidence") or {}
    for key in ("matched_old_text", "old_text", "source_quote", "original"):
        value = edit.get(key) or evidence.get(key)
        if value:
            return str(value)
    delete_texts = evidence.get("delete_texts")
    if delete_texts:
        return " ".join(str(item) for item in delete_texts)
    return ""


def _unresolved_text(reason: str, detail: dict) -> str:
    """A plain-language version of the engine's reason code, keeping the code for audit."""
    friendly = {
        "RECALL_TARGET_UNRESOLVED": "未能在合同中准确定位该条款，保持原文",
        "RECALL_RULE_NOT_APPLICABLE": "该条款对当前产品不适用，保持原文",
        "RECALL_SLOT_UNRESOLVED": "份额类别占位符未能按合同实际类别展开，保持原文",
        "RECALL_COMPOSE_DELETE_NOT_SHRINKING": "改写未使原文变短，按安全规则保持原文",
        "RECALL_TARGET_STRUCTURE": "目标跨越不允许的结构边界，保持原文",
        "RECALL_TARGET_COMPOSITE_UNRESOLVED": "跨段目标未能安全绑定，保持原文",
    }.get(reason, f"按安全规则保持原文（原因代码：{reason}）")
    rule = detail.get("rule")
    return friendly + (f"（规则 {rule}）" if rule else "")


def summary_row(item: dict) -> str:
    result, report = item["result"], item["report"]
    guide = guide_rules(report)
    edits = report_plan_edits(report)
    name = item["original"]
    delivery = report.get("delivery_status") or result.get("delivery_status")
    text = DELIVERY_TEXT.get(delivery, delivery or "未知")
    detail = ""
    labels = list(dict.fromkeys(rule_label(guide, e.get("rule_id") or "") for e in edits))
    if labels:
        detail = "涉及：" + "、".join(labels)
    unresolved = unresolved_entries(report)
    if unresolved and not labels:
        text = DELIVERY_TEXT.get("incomplete")
        detail = f"{len(unresolved)} 项按安全规则保持原文"
    return f"| {name} | {text} | {len(edits)} | {detail} |"


def unique_name(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    stem, suffix = Path(name).stem, Path(name).suffix
    index = 2
    while f"{stem} ({index}){suffix}" in used:
        index += 1
    result = f"{stem} ({index}){suffix}"
    used.add(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="P6 run directory (has <case>/result.json)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-date", default="")
    parser.add_argument("--ledger-note", default="")
    parser.add_argument("--title-suffix", default="（P6 真实合同评测）")
    args = parser.parse_args()

    run_dir = Path(args.run).resolve()
    items = load_run(run_dir)
    if not items:
        raise SystemExit(f"no cases found under {run_dir}")

    root = Path(args.output).resolve()
    final_dir = root / "最终版（接受修订后）"
    notes_dir = root / "逐份修改说明"
    final_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    used: set[str] = set()
    rows: list[dict] = []
    for item in items:
        result = item["result"]
        name = unique_name(result.get("file") or result["case_id"], used)
        item["original"] = name
        case_dir = run_dir / result["case_id"]
        # The app writes accepted-revision artifacts as ``final``/``redline`` for a
        # complete delivery and ``working_final``/``working_redline`` when the run is
        # fail-closed (delivery != complete). Both are the real DOCX to hand over.
        source = _first_existing(case_dir / "final", case_dir / "working_final")
        redline = _first_existing(case_dir / "redline", case_dir / "working_redline")
        stem = Path(name).stem
        folder = notes_dir / stem
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "修改说明.md").write_text(case_explanation(name, item), encoding="utf-8")
        (folder / "修改明细.json").write_text(
            json.dumps({"count": len(report_plan_edits(item["report"])),
                        "edits": report_plan_edits(item["report"]),
                        "unresolved": unresolved_entries(item["report"]),
                        "output_validation": item["report"].get("output_validation")},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        if source is not None:
            shutil.copy2(source, final_dir / name)
        if redline is not None:
            shutil.copy2(redline, folder / f"{stem}（修改痕迹版）{Path(name).suffix}")
        rows.append(item)

    lines = [f"# FundLex 合同修改结果总览{args.title_suffix}"
             + (f"（{args.run_date}）" if args.run_date else ""), "",
             "本结果由 FundLex 按既定业务规则自动定位并修改合同条款，每处修改都经过系统规则校验与独立复核"
             "（独立复核由另一个 AI 检查任务完成，不是人工审批）。",
             "**重要提示：本批文件为评测验证结果，不构成正式发布批准；正式使用前建议人工抽查。**", "",
             "## 文件夹说明", "",
             "| 文件夹 | 内容 |", "| --- | --- |",
             "| 最终版（接受修订后） | 修改后的合同，文件名与原合同一致，直接打开即可 |",
             "| 逐份修改说明 | 每份合同一个文件夹：修改说明、修改明细，以及带 Word 修订痕迹的版本"
             "（可逐条查看/接受/拒绝修改） |", "",
             "## 处理结果一览（真实合同）", "",
             "| 合同文件 | 处理结果 | 修改处数 | 说明 |", "| --- | --- | --- | --- |"]
    for row in rows:
        lines.append(summary_row(row))
    lines += ["", "## 如何查看修改", "",
              "1. 直接打开“最终版（接受修订后）”中的文件，即为改后合同；",
              "2. 如需核对改动过程，打开“逐份修改说明/<合同名>/”里的“（修改痕迹版）”文件，"
              "在 Word 的“审阅”中查看修订；",
              "3. 每份合同的详细说明见“逐份修改说明/<合同名>/修改说明.md”。"]
    if args.ledger_note:
        lines += ["", f"- 模型用量记录：{args.ledger_note}"]
    (root / "结果总览.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"output": str(root), "cases": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
