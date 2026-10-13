"""Build the user-facing result package from v2 evaluation runs.

Layout (business-reader oriented):

    <output>/
      结果总览.md
      最终版（接受修订后）/            所有合同的接受修订后文件，文件名与原件一致
      修改痕迹版/                     同样的文件，带 Word 修订痕迹，便于查看改了什么
      逐份修改说明/<合同名>/           修改说明.md + 修改明细.json
      未修改（整份排除）/              类型排除合同的未改动原件副本
      供参考-构造测试件/               构造样例（非真实合同）的产物与说明

Cohorts are declared as ``label|run_dir|selection_json|kind`` where ``kind`` is
``real`` or ``fixture``. ``selection_json`` maps uploaded copies back to the
original contract file names.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ACTION_NAMES = {
    "R01-A1": "在“释义”章节补充直销机构费用豁免条款",
    "R02-A1": "在“基金的基本情况”补充直销机构费用豁免条款",
    "R03-A3": "删除份额类别设置中的“并报中国证监会备案”表述",
    "R04-A1": "删除“不同份额类别不得互相转换”的旧限制句",
    "R11-A1": "删除费率调整段中的“7 日短期持有赎回费”旧句",
    "R10-A1": "把赎回费归属条款改为“赎回费用全额计入基金财产”",
}
ACTION_SHORT = {
    "R01-A1": "补充直销豁免（释义）",
    "R02-A1": "补充直销豁免（基本情况）",
    "R03-A3": "删除备案表述",
    "R04-A1": "删除禁止转换旧句",
    "R11-A1": "删除 7 日赎回费旧句",
    "R10-A1": "改为全额计入基金财产",
}
REASON_TEXT = {
    "V2_FACT_ROLE_MISMATCH": "系统核对时无法把生成内容中的依据对应到合同原文，按安全规则保持原文",
    "CROSS_PARAGRAPH_TARGET_UNSUPPORTED": "目标内容跨段落，当前版本不支持安全修改，保持原文",
    "V2_TARGET_NOT_LOCATED": "未能在合同中准确定位该条款，保持原文",
    "V2_EXISTING_CLAUSE_UNSUPPORTED": "该段落已包含部分直销条款，为避免重复或冲突保持原文",
    "V2_HYBRID_CLASS_FEE_UNSUPPORTED": "存在同时收取两种费用的类别，无法安全套用统一规则，保持原文",
    "V2_CLASS_DEFINITION_CONFLICT": "合同中的类别与收费信息不一致，保持原文",
    "PROFILE_EVIDENCE_INCOMPLETE": "类别收费信息不完整，无法确认，保持原文",
    "SHORT_HOLDING_NON_TARGET_HOST": "该句属于费用归属条款（由另一项规则处理），本项不修改",
    "V2_ALREADY_SATISFIED": "原合同已符合要求，无需修改",
    "TARGET_SCOPE_UNRESOLVED": "合同中未找到相应章节",
    "V2_VERIFY_NOT_SATISFIED": "独立复核认为改写未完全满足要求，保持原文",
    "V2_VERIFY_QUOTE_MISMATCH": "独立复核引用的原文无法核对，保持原文",
    "V2_CONTENT_CHECK_FAILED": "改写内容未通过规则校验，保持原文",
    "MODEL_SCHEMA_INVALID": "模型返回格式不符合要求，保持原文",
    "MODEL_QUOTE_MISMATCH": "模型引用的原文无法核对，保持原文",
    "V2_SOURCE_QUOTE_MISMATCH": "模型定位的原文与系统记录不一致，保持原文",
    "V2_REPLACEMENT_UNCHANGED": "改写内容与原文相同，无需修改",
    "REQUIREMENT_UNKNOWN": "无法确认该条款是否满足要求，保持原文",
}
DELIVERY_TEXT = {
    "evaluation_modified": "已修改",
    "evaluation_unmodified": "无需修改（原合同已符合）",
    "incomplete": "部分条款未修改（详见修改说明）",
    "not_generated": "整份排除，未修改",
}
FIXTURE_NOTE = "以下为系统自建的构造样例（非真实合同），用于验证特殊情形；保留仅供技术参考。"
EXCLUSION_NOTE = "以下合同属于整份排除类型（如 ETF、同业存单、货币型基金），系统未做任何修改，附上原件副本。"


def load_items(run: Path) -> list[dict]:
    items = []
    for path in sorted(run.glob("batch_*.json")):
        items.extend(json.loads(path.read_text(encoding="utf-8")))
    return items


def selection_entries(path: Path | None) -> list[dict]:
    if path is None:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("cases", [])


def load_inputs(run: Path, selection: Path | None) -> dict[str, Path]:
    """Map uploaded basenames to readable source paths (manifest first, then selection)."""
    mapping: dict[str, Path] = {}
    selection_entries_list = selection_entries(selection)
    for entry in selection_entries_list:
        if entry.get("input"):
            mapping[Path(entry["input"]).name] = Path(entry["input"])
    manifest_path = run / "manifest.json"
    if manifest_path.is_file():
        for entry in json.loads(manifest_path.read_text(encoding="utf-8")):
            mapping[Path(entry["file"]).name] = Path(entry["file"])
    return mapping


def load_names(selection: Path | None) -> dict[str, str]:
    mapping = {}
    for entry in selection_entries(selection):
        input_name = entry.get("input")
        original = entry.get("original_file")
        if input_name and original:
            mapping[Path(input_name).name] = Path(original).name
    return mapping


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


def reason_text(code: str | None) -> str:
    if not code:
        return "—"
    return REASON_TEXT.get(code, f"系统按安全规则保持原文（原因代码：{code}）")


def case_report(name: str, item: dict, cohort: str) -> str:
    report = item["report"]
    edits = report.get("edit_plan", {}).get("edits", [])
    actions = report.get("actions", [])
    failed = []
    for action in actions:
        if action["status"] in {"failed", "partial"}:
            reasons = []
            for target in action.get("targets", []):
                if target.get("status") == "failed" and target.get("reason"):
                    reasons.append(target["reason"])
            failed.append((action["action_id"], action.get("failure_reason") or (reasons[0] if reasons else "未知原因")))
    lines = [f"# {name} 修改说明", "",
             f"- 来源：{cohort}",
             f"- 处理结果：{DELIVERY_TEXT.get(report.get('delivery_status'), report.get('delivery_status'))}",
             f"- 实际修改：{len(edits)} 处" + (f"；未修改：{len(failed)} 项（原因见下）" if failed else ""),
             ""]
    if report.get("qualification_status") == "excluded_by_fund_type":
        lines += ["本合同属于整份排除类型（ETF、同业存单、货币型或其他明确排除类型），系统未做任何修改。", ""]
    if edits:
        lines += ["## 修改清单", "",
                  "| 序号 | 修改内容 | 修改前（节选） | 修改后（节选） | 校验 |",
                  "| --- | --- | --- | --- | --- |"]
        for index, edit in enumerate(edits, start=1):
            action = edit.get("action_id")
            record = edit.get("verification") or {}
            passed = "通过（规则校验＋独立复核）" if record.get("passed") else "未通过"
            before = "（保留原文，在其后追加新条款）" if edit.get("operation") == "insert" else str(edit.get("expected_old_text", ""))[:120]
            after = "（删除该句）" if not edit.get("replacement") else str(edit.get("replacement", ""))[:160]
            lines.append(f"| {index} | {ACTION_NAMES.get(action, action)} | {before} | {after} | {passed} |")
        lines.append("")
    if failed:
        lines += ["## 未修改的内容及原因", "",
                  "| 条款 | 原因 |", "| --- | --- |"]
        seen = set()
        for action, reason in failed:
            key = (action, reason)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"| {ACTION_NAMES.get(action, action)} | {reason_text(reason)} |")
        lines.append("")
        lines.append("以上未修改项保持原合同文字，不会造成错误改动；如需修改请人工处理。")
        lines.append("")
    lines += ["## 怎么核对", "",
              "- 打开“最终版（接受修订后）”中的同名文件即为改后版本；",
              "- 本文件夹内的“（修改痕迹版）”文件带 Word 修订痕迹，可逐条查看、接受或拒绝修改；",
              "- 本说明的表格与文件内容一一对应，可对照抽查。",
              ""]
    validation = report.get("output_validation") or {}
    lines += ["## 追溯信息（如需审计再看）", "",
              f"- 源文件 SHA-256：{report.get('source_sha256')}",
              f"- 修改后文件 SHA-256：{validation.get('final_sha256')}",
              f"- 修改痕迹版 SHA-256：{validation.get('redline_sha256')}",
              f"- 规则版本：v2（{report.get('ruleset_sha256')}）",
              f"- 引擎标识（技术追溯）：{report.get('engine_build')}",
              f"- 验证记录：{len(report.get('content_verifications', []))} 条（服务端生成并绑定原文与新文）",
              "- 提示：本文件为评测验证结果，正式使用前建议人工抽查，不构成正式发布批准。"]
    return "\n".join(lines) + "\n"


def build_cohort(items: list[dict], names: dict[str, str], used: set[str]) -> list[dict]:
    rows = []
    for item in items:
        uploaded = item["name"]
        original = names.get(uploaded, uploaded)
        report = item["report"]
        edits = report.get("edit_plan", {}).get("edits", [])
        failed = [action for action in report.get("actions", []) if action["status"] in {"failed", "partial"}]
        rows.append({"item": item, "uploaded": uploaded, "original": unique_name(original, used),
                     "delivery": report.get("delivery_status"), "edits": len(edits), "failed": failed})
    return rows


def copy_outputs(rows: list[dict], final_dir: Path, notes_dir: Path, cohort: str) -> None:
    for row in rows:
        item, name = row["item"], row["original"]
        stem = Path(name).stem
        folder = notes_dir / stem
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "修改说明.md").write_text(case_report(name, item, cohort), encoding="utf-8")
        (folder / "修改明细.json").write_text(
            json.dumps(item["report"].get("edit_plan", {}), ensure_ascii=False, indent=2), encoding="utf-8")
        if item.get("final_docx") and Path(item["final_docx"]).is_file():
            final_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item["final_docx"], final_dir / name)
        if item.get("redline_docx") and Path(item["redline_docx"]).is_file():
            # The tracked-changes copy lives with its own explanation folder.
            redline_name = f"{stem}（修改痕迹版）{Path(name).suffix}"
            shutil.copy2(item["redline_docx"], folder / redline_name)


def summary_row(row: dict) -> str:
    report = row["item"]["report"]
    delivery = DELIVERY_TEXT.get(row["delivery"], row["delivery"])
    detail = ""
    if row["delivery"] == "incomplete":
        reasons = []
        for action in row["failed"]:
            target_reason = next((target.get("reason") for target in action.get("targets", [])
                                  if target.get("status") == "failed" and target.get("reason")), None)
            reasons.append(f"{ACTION_SHORT.get(action['action_id'], action['action_id'])}："
                           f"{reason_text(target_reason or action.get('failure_reason'))}")
        detail = "；".join(dict.fromkeys(reasons))
    elif report.get("qualification_status") == "excluded_by_fund_type":
        detail = "整份排除类型，未修改"
    elif row["edits"]:
        actions = "、".join(dict.fromkeys(ACTION_SHORT.get(edit["action_id"], edit["action_id"])
                                          for edit in report.get("edit_plan", {}).get("edits", [])))
        detail = f"涉及：{actions}"
    return f"| {row['original']} | {delivery} | {row['edits']} | {detail} |"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--cohort", action="append", required=True,
                        help="label|run_dir|selection_json|kind (kind=real|fixture)")
    parser.add_argument("--ledger-note", default="")
    parser.add_argument("--run-date", default="")
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    real_rows, fixture_rows, excluded_rows = [], [], []
    real_final, real_notes = (root / "最终版（接受修订后）", root / "逐份修改说明")
    fixture_root = root / "供参考-构造测试件"
    excluded_dir = root / "未修改（整份排除）"
    used: set[str] = set()
    for spec in args.cohort:
        label, run_dir, selection, kind = [part.strip() for part in spec.split("|")]
        items = load_items(Path(run_dir).resolve())
        names = load_names(Path(selection).resolve() if selection else None)
        inputs = load_inputs(Path(run_dir).resolve(), Path(selection).resolve() if selection else None)
        rows = build_cohort(items, names, used)
        if kind == "fixture":
            copy_outputs(rows, fixture_root / "最终版", fixture_root / "逐份修改说明", label)
            fixture_rows.extend([{**row, "cohort": label} for row in rows])
        else:
            copy_outputs(rows, real_final, real_notes, label)
            for row in rows:
                row["cohort"] = label
                if row["delivery"] == "not_generated" and row["item"]["report"].get("qualification_status") == "excluded_by_fund_type":
                    excluded_dir.mkdir(parents=True, exist_ok=True)
                    input_copy = inputs.get(row["uploaded"])
                    if input_copy and input_copy.is_file():
                        shutil.copy2(input_copy, excluded_dir / row["original"])
                    excluded_rows.append({**row, "cohort": label})
                else:
                    real_rows.append(row)
    lines = [f"# FundLex 合同修改结果总览{'（' + args.run_date + '）' if args.run_date else ''}", "",
             "本结果由 FundLex 按既定业务规则自动定位并修改合同条款，每处修改都经过系统规则校验与独立复核"
             "（独立复核由另一个 AI 检查任务完成，不是人工审批）。",
             "**重要提示：本批文件为评测验证结果，不构成正式发布批准；正式使用前建议人工抽查。**", "",
             "## 文件夹说明", "",
             "| 文件夹 | 内容 |", "| --- | --- |",
             "| 最终版（接受修订后） | 修改后的合同，文件名与原合同一致，直接打开即可 |",
             "| 逐份修改说明 | 每份合同一个文件夹：修改说明、修改明细，以及带 Word 修订痕迹的版本（可逐条查看/接受/拒绝修改） |",
             "| 未修改（整份排除） | 属于整份排除类型的合同原件副本（未做任何修改） |",
             "| 供参考-构造测试件 | 系统自建样例（非真实合同），用于验证特殊情形 |", "",
             "## 处理结果一览（真实合同）", "",
             "| 合同文件 | 处理结果 | 修改处数 | 说明 |", "| --- | --- | --- | --- |"]
    for row in real_rows + excluded_rows:
        lines.append(summary_row(row))
    if excluded_rows:
        lines += ["", EXCLUSION_NOTE]
    if fixture_rows:
        lines += ["", "## 构造测试件（非真实合同）", "", FIXTURE_NOTE, "",
                  "| 测试件 | 处理结果 | 修改处数 | 说明 |", "| --- | --- | --- | --- |"]
        for row in fixture_rows:
            lines.append(summary_row(row))
    lines += ["", "## 如何查看修改", "",
              "1. 直接打开“最终版（接受修订后）”中的文件，即为改后合同；",
              "2. 如需核对改动过程，打开“逐份修改说明/<合同名>/”里的“（修改痕迹版）”文件，在 Word 的“审阅”中查看修订；",
              "3. 每份合同的详细说明见“逐份修改说明/<合同名>/修改说明.md”。"]
    if args.ledger_note:
        lines += ["", f"- 模型用量记录：{args.ledger_note}"]
    (root / "结果总览.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(root), "real": len(real_rows), "excluded": len(excluded_rows),
                      "fixtures": len(fixture_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
