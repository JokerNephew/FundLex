"""Build the user-facing result package from a recall-first (P6) run directory.

The layout mirrors the earlier business-reader package (see
``FundLex-合同修改结果-本次抽查-20261013``) so the deliverable reads the same way:

    <output>/
      结果总览.md                              每份合同改了几处、涉及哪些条款
      结果清单.csv                              与工作台「导出结果清单」同格式的状态清单
      最终版（接受修订后）/<原合同名>.docx     接受修订后的改后合同（单独一个文件夹）
      逐份修改说明/<原合同名>/
          修改说明.md                          逐处列出「改之前 / 改之后」
          修改明细.json
          <原合同名>（全量痕迹版）.docx        引擎全部修订痕迹，可逐条接受/拒绝
          <原合同名>（选择修订版）.docx        仅人工选择保留的修订（有选择时才生成）

The recall-first engine's report differs from the v2 one: it uses ``plan.edits`` with
``rule_id`` (G01..G22), ``location`` (pNNN), ``operation`` (insert/replace) and a
``replacement`` string, and the guide carries the per-rule titles/requirements. This tool
maps those onto the readable tables the reference package uses, without inventing content:
every row comes from the run's own report/plan, the source DOCX and the guide.

The edit extraction itself lives in :mod:`fundlex.edit_summary` so the workbench
(its ZIP archive and task overview) and this offline tool can never drift apart.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from fundlex.edit_summary import (CLIP_LIMIT_BEFORE, CLIP_LIMIT_AFTER,
                                  audit_verdicts, clip as _clip,
                                  delivery_text, edit_before_after, edit_count,
                                  operation_text, plan_edits, rule_label,
                                  rule_requirement, summary_detail,
                                  unresolved_entries, verdict_text)


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


def guide_rules(report: dict) -> dict:
    return (report.get("guide") or {})


def failed_targets(report: dict) -> list[dict]:
    """Targets the engine could not resolve, with its own reason text (verbatim)."""
    out: list[dict] = []
    for target in report.get("targets") or []:
        if target.get("state") == "needs_edit" and target.get("status") not in {
                "planned", "satisfied", "not_applicable"}:
            out.append(target)
    return out


def case_explanation(name: str, item: dict) -> str:
    result, report = item["result"], item["report"]
    guide = guide_rules(report)
    edits = plan_edits(report)
    lines = [f"# {name} 修改说明", "",
             "- 来源：P6 真实合同评测（应用链路：上传→真实模型→DOCX 修改→复核）",
             f"- 处理结果：{delivery_text(report, result)}",
             f"- 实际修改：{edit_count(report)} 处（下表逐处对照「改之前 / 改之后」）"]
    unresolved = unresolved_entries(report)
    if unresolved:
        lines[-1] += f"；未修改：{len(unresolved)} 项（原因见下）"
    lines.append("")

    verdicts = audit_verdicts(report)
    if edits:
        lines += ["## 逐处修改对照", "",
                  "| 序号 | 修改内容 | 位置 | 操作 | 修改前（节选） | 修改后（节选） | 校验 |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for index, edit in enumerate(edits, start=1):
            rule_id = edit.get("rule_id") or ""
            label = rule_label(guide, rule_id)
            before, after = edit_before_after(edit)
            verdict = next((verdicts.get(part.strip()) for part in str(rule_id).split("+")
                            if verdicts.get(part.strip())), None)
            op = operation_text(edit)
            lines.append(f"| {index} | {label} | {edit.get('location') or '—'} | {op} "
                         f"| {_clip(before, CLIP_LIMIT_BEFORE) or '—'} "
                         f"| {_clip(after, CLIP_LIMIT_AFTER) or '—'} "
                         f"| {verdict_text(verdict)} |")
        lines.append("")
        lines += ["### 逐处修改详情", "",
                  "以下逐处写明修改前的合同原文与修改后的文字（节选），完整上下文请看"
                  "本文件夹内的“（全量痕迹版）”。", ""]
        for index, edit in enumerate(edits, start=1):
            rule_id = edit.get("rule_id") or ""
            label = rule_label(guide, rule_id)
            before, after = edit_before_after(edit)
            op = operation_text(edit)
            requirement = rule_requirement(guide, rule_id.split("+")[0].strip())
            lines.append(f"#### 第 {index} 处 · {label}")
            lines.append(f"- 位置：{edit.get('location') or '—'}（操作：{op}）")
            if requirement:
                lines.append(f"- 指引要求：{requirement}")
            lines += ["- **修改前**：", "", "  > " + (before or "（无）").replace("\n", " "), "",
                      "- **修改后**：", "", "  > " + (after or "（无）").replace("\n", " "), ""]
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
              "- 本文件夹内的“（全量痕迹版）”文件带全部 Word 修订痕迹，可逐条查看、"
              "接受或拒绝修改；若有“（选择修订版）”，其中只保留人工接受的修订，"
              "接受其全部修订即得到“最终版（接受修订后）”；",
              "- 本说明的表格与文件内容一一对应，可对照抽查。",
              ""]

    validation = report.get("output_validation") or {}
    model = report.get("model") or {}
    lines += ["## 追溯信息（如需审计再看）", "",
              f"- 源文件 SHA-256：{report.get('source_sha256') or result.get('sha256')}",
              f"- 修改后文件 SHA-256：{validation.get('final_sha256')}",
              f"- 引擎修订痕迹版（全量）SHA-256：{validation.get('redline_sha256')}",
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
    name = item["original"]
    text = delivery_text(report, result)
    detail = summary_detail(report, result)
    return f"| {name} | {text} | {edit_count(report)} | {detail} |"


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


# ── 结果清单.csv (same columns as the workbench "导出结果清单") ──────────────────────
# The frontend writes ["序号","文件名","资格","处理状态","交付完整性","业务提示","原始原因码"];
# reproducing it here means the packaged folder carries the same status list a user would
# download from the workbench (a state list, not the contract deliverable).
CSV_LABELS = {
    "eligible": "资格符合", "excluded_by_fund_type": "已排除", "pending": "未判定",
    "completed": "处理完成", "succeeded": "已处理", "failed": "失败关闭",
    "complete": "产物完整", "incomplete": "结果不完整", "not_generated": "未生成",
    "complete_with_exceptions": "已交付（含例外条款）",
}


def delivery_reason(report: dict, result: dict) -> str:
    """The workbench's ``docReason`` wording for this document's most important state."""
    qualification = (report.get("qualification_status")
                     or (result.get("qualification") or {}).get("status"))
    if qualification == "excluded_by_fund_type":
        return "基金类型不在本流程范围，已整份排除"
    delivery = report.get("delivery_status") or result.get("delivery_status")
    if delivery == "complete":
        return "文件校验通过，仍需结合自动写入能力判断可用性"
    if delivery == "complete_with_exceptions":
        return "合同已修订并校验通过；有条款未自动修改，请按例外清单人工核对"
    if delivery == "incomplete":
        return "部分条款未修改或处理未完整结束，不能直接使用"
    if delivery == "not_generated":
        return "处理已结束，未生成可交付合同文件"
    if result.get("job_status") == "succeeded":
        return "处理已结束，未生成可交付合同文件"
    return "尚未生成合同产物"


def reason_codes(report: dict) -> str:
    """Distinct short machine codes behind the outcome, for the 原始原因码 column.

    The workbench exports short codes (``RECALL_…``/``AUDIT_…``), never the model's prose
    explanation, so audit entries contribute their ``code`` and only ``reason`` values that
    look like a code (upper-case snake) are taken from target entries.
    """
    def looks_like_code(value: object) -> bool:
        text = str(value or "")
        return bool(text) and text.replace("_", "").isalnum() and text.upper() == text

    codes: list[str] = []
    for entry in report.get("unresolved") or []:
        code = entry.get("code")
        if not code and looks_like_code(entry.get("reason")):
            code = entry.get("reason")
        if code and code not in codes:
            codes.append(code)
    for finding in (report.get("sweep") or {}).get("findings") or []:
        if finding.get("status") in {"pending", "unresolved"}:
            code = finding.get("code")
            if code and code not in codes:
                codes.append(code)
    return "；".join(codes)


def csv_escape(value: object) -> str:
    text = "" if value is None else str(value)
    if any(char in text for char in '",\n\r'):
        return '"' + text.replace('"', '""') + '"'
    return text


def build_result_csv(rows: list[dict]) -> str:
    """Reproduce the workbench's exported 结果清单.csv content (BOM + CRLF rows)."""
    header = ["序号", "文件名", "资格", "处理状态", "交付完整性", "业务提示", "原始原因码"]
    lines = [",".join(header)]
    for index, item in enumerate(rows, start=1):
        report, result = item["report"], item["result"]
        qualification = (report.get("qualification_status")
                         or (result.get("qualification") or {}).get("status") or "pending")
        job_status = result.get("job_status") or report.get("job_status") or ""
        delivery = report.get("delivery_status") or result.get("delivery_status") or ""
        cells = [index, item["original"],
                 CSV_LABELS.get(qualification, qualification),
                 CSV_LABELS.get(job_status, job_status),
                 CSV_LABELS.get(delivery, delivery),
                 delivery_reason(report, result),
                 reason_codes(report)]
        lines.append(",".join(csv_escape(cell) for cell in cells))
    return "\ufeff" + "\r\n".join(lines) + "\r\n"


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
        # A reviewed contract additionally has the post-review selection; it wins for
        # the final version, and its revision file is shipped alongside the engine's.
        source = _first_existing(case_dir / "selected_final",
                                 case_dir / "final", case_dir / "working_final")
        engine_redline = _first_existing(case_dir / "redline", case_dir / "working_redline",
                                         case_dir / "selected_redline")
        selected_redline = _first_existing(case_dir / "selected_redline")
        stem = Path(name).stem
        folder = notes_dir / stem
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "修改说明.md").write_text(case_explanation(name, item), encoding="utf-8")
        (folder / "修改明细.json").write_text(
            json.dumps({"count": edit_count(item["report"]),
                        "edits": plan_edits(item["report"]),
                        "unresolved": unresolved_entries(item["report"]),
                        "output_validation": item["report"].get("output_validation")},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        if source is not None:
            shutil.copy2(source, final_dir / name)
        suffix = Path(name).suffix
        if engine_redline is not None:
            shutil.copy2(engine_redline, folder / f"{stem}（全量痕迹版）{suffix}")
        if selected_redline is not None:
            shutil.copy2(selected_redline, folder / f"{stem}（选择修订版）{suffix}")
        rows.append(item)

    # The workbench's 结果清单.csv, reproduced for the packaged folder (root level).
    (root / "结果清单.csv").write_text(build_result_csv(rows), encoding="utf-8")

    lines = [f"# FundLex 合同修改结果总览{args.title_suffix}"
             + (f"（{args.run_date}）" if args.run_date else ""), "",
             "本结果由 FundLex 按既定业务规则自动定位并修改合同条款，每处修改都经过系统规则校验与独立复核"
             "（独立复核由另一个 AI 检查任务完成，不是人工审批）。",
             "**重要提示：本批文件为评测验证结果，不构成正式发布批准；正式使用前建议人工抽查。**", "",
             "## 文件夹说明", "",
             "| 文件夹 | 内容 |", "| --- | --- |",
             "| 结果清单.csv | 工作台「导出结果清单」同格式的状态清单（序号/文件名/资格/处理状态/"
             "交付完整性/业务提示/原始原因码），供筛选汇总 |",
             "| 最终版（接受修订后） | 全部已接受修订的改后合同，文件名与原合同一致，直接打开即可 |",
             "| 逐份修改说明 | 每份合同一个文件夹：修改说明（逐处列出「改之前 / 改之后」）、修改明细，"
             "以及带 Word 修订痕迹的版本。「（全量痕迹版）」为引擎全部改动；"
             "若在工作台把部分修订改为不接受，另附「（选择修订版）」，只保留接受的修订 |", "",
             "## 每份合同的修改情况", "",
             "下表逐份列出合同改了几处、涉及哪些条款；详细对照见“逐份修改说明/<合同名>/修改说明.md”。", "",
             "| 合同文件 | 处理结果 | 修改处数 | 涉及条款 |", "| --- | --- | --- | --- |"]
    for row in rows:
        lines.append(summary_row(row))
    lines += ["", "## 如何查看修改", "",
              "1. 直接打开“最终版（接受修订后）”中的文件，即为改后合同；",
              "2. 如需核对改动过程，打开“逐份修改说明/<合同名>/”里的“（全量痕迹版）”文件，"
              "在 Word 的“审阅”中查看引擎的全部修订；若有“（选择修订版）”，"
              "它只含人工接受的修订，接受其全部修订即得到最终版；",
              "3. 每份合同的详细说明见“逐份修改说明/<合同名>/修改说明.md”。"]
    if args.ledger_note:
        lines += ["", f"- 模型用量记录：{args.ledger_note}"]
    (root / "结果总览.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"output": str(root), "cases": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
