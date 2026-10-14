"""Build a human-readable handover package from a v2 evaluation run.

Copies the downloaded evaluation DOCX files, per-contract reports, edit plans
and server-side verification records into case folders with a summary table.
The package contains contract text: keep it outside the repository.

Run::

    .venv\\Scripts\\python.exe -X utf8 -m tools.evaluation.v2_handover \\
        --run <run dir> --output <package dir> --label 16份-回归集
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def load_items(run: Path) -> list[dict]:
    items = []
    for path in sorted(run.glob("batch_*.json")):
        items.extend(json.loads(path.read_text(encoding="utf-8")))
    return items


def case_markdown(item: dict) -> str:
    report = item["report"]
    lines = [f"# {Path(item['name']).stem} 处理报告（评测模式，不构成正式最终合同）", "",
             f"- 规则版本：{report.get('ruleset_version')} / {report.get('ruleset_sha256')}",
             f"- 引擎：{report.get('engine_build')}",
             f"- 资格：{report.get('qualification_status')}",
             f"- 执行模式：{report.get('execution_mode')}",
             f"- 交付状态：{report.get('delivery_status')}",
             f"- 修改数：{report.get('edit_plan', {}).get('count', 0)}"]
    if report.get("error_code"):
        lines.append(f"- 错误代码：{report['error_code']}")
    validation = report.get("output_validation") or {}
    if validation:
        lines += ["", "## 产物校验", "",
                  f"- 类型：{validation.get('kind')}",
                  f"- 检查：{', '.join(validation.get('checks', []))}",
                  f"- 红线 SHA-256：{validation.get('redline_sha256')}",
                  f"- 接受修订后 SHA-256：{validation.get('final_sha256')}"]
    lines += ["", "## 修改明细", ""]
    edits = report.get("edit_plan", {}).get("edits", [])
    if not edits:
        lines.append("无修改（未命中目标、已符合或按规则拒绝）。")
    for edit in edits:
        record = edit.get("verification") or {}
        lines.append(f"### {edit.get('action_id')} @ {edit.get('location')} [{edit.get('start')},{edit.get('end')})")
        lines.append("")
        lines.append(f"- 原文：{str(edit.get('expected_old_text'))[:300]}")
        lines.append(f"- 新文：{str(edit.get('replacement'))[:300]}")
        lines.append(f"- 内容来源：{record.get('content_source')}；服务端验证：{'通过' if record.get('passed') else '未通过'}")
        lines.append(f"- 验证记录 SHA-256：{record.get('record_sha256')}")
        for requirement in record.get("requirements", []):
            lines.append(f"  - {requirement.get('id')}（{requirement.get('checker')}）：{requirement.get('result')}")
        verify = record.get("model_verify")
        if verify:
            lines.append(f"  - 独立验证模型：{verify.get('actual_model')}；项目：{len(verify.get('items', []))}")
            for verify_item in verify.get("items", []):
                lines.append(f"    - {verify_item.get('requirement_id')}：{verify_item.get('result')}"
                             f"（{verify_item.get('evidence_source')}）{str(verify_item.get('evidence_quote'))[:80]}")
        lines.append("")
    lines += ["", "## 全部动作状态", ""]
    for action in report.get("actions", []):
        lines.append(f"- {action['action_id']}：{action['status']}；适用性 {action['applicability']}；"
                     f"目标 {len(action.get('targets', []))}；{action.get('failure_reason') or '无失败'}")
        for target in action.get("targets", []):
            lines.append(f"  - {target['location']} [{target['char_start']},{target['char_end']})："
                         f"{target['status']}；{target.get('reason') or '核验通过'}")
    lines.append("")
    lines.append("**评测产物，不构成可直接使用的正式最终合同。**")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    run = Path(args.run).resolve()
    root = Path(args.output).resolve() / args.label
    root.mkdir(parents=True, exist_ok=True)
    items = load_items(run)
    summary = []
    for item in items:
        stem = Path(item["name"]).stem
        folder = root / stem
        folder.mkdir(exist_ok=True)
        report = item["report"]
        for kind, source in (("evaluation_final", item.get("final_docx")),
                             ("evaluation_redline", item.get("redline_docx"))):
            if source and Path(source).is_file():
                shutil.copy2(source, folder / f"{stem}_{kind}.docx")
        (folder / f"{stem}_report.md").write_text(case_markdown(item), encoding="utf-8")
        (folder / f"{stem}_edits.json").write_text(
            json.dumps(report.get("edit_plan", {}), ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / f"{stem}_content_verification.json").write_text(
            json.dumps(report.get("content_verifications", []), ensure_ascii=False, indent=2), encoding="utf-8")
        summary.append({
            "case": stem, "qualification": report.get("qualification_status"),
            "delivery": report.get("delivery_status"), "edits": report.get("edit_plan", {}).get("count", 0),
            "actions": {action["action_id"]: action["status"] for action in report.get("actions", [])
                        if action["status"] not in {"not_matched", "not_applicable"}},
            "final_sha256": (report.get("output_validation") or {}).get("final_sha256"),
            "redline_sha256": (report.get("output_validation") or {}).get("redline_sha256"),
        })
    lines = [f"# {args.label} 结果汇总", "",
             f"- 运行目录：{run}",
             f"- 合同数：{len(summary)}",
             "", "| 合同 | 资格 | 交付状态 | 修改数 | 动作状态 | 接受修订后 SHA-256 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in summary:
        actions = "；".join(f"{key}={value}" for key, value in row["actions"].items()) or "—"
        lines.append(f"| {row['case']} | {row['qualification']} | {row['delivery']} | {row['edits']} "
                     f"| {actions} | {(row['final_sha256'] or '')[:16]} |")
    (root / "汇总.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "汇总.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(root), "cases": len(summary),
                      "modified": sum(1 for row in summary if row["edits"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
