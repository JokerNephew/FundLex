"""Aggregate real-run evidence per action for the release report (read-only).

Reads one or more v2 evaluation run directories (batch_*.json) and writes a
per-action execution/refusal/artifact summary. No model calls.

Run::

    .venv\\Scripts\\python.exe -X utf8 -m tools.evaluation.release_evidence \\
        --run pilot=<dir> --run unseen=<dir> --run fixtures=<dir> --output docs/RELEASE_EVIDENCE.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def load_reports(run: Path) -> list[dict]:
    batches = sorted(run.glob("batch_*.json"))
    if batches:
        return [item["report"] for path in batches
                for item in json.loads(path.read_text(encoding="utf-8"))]
    summary = run / "summary.json"
    if summary.is_file():
        data = json.loads(summary.read_text(encoding="utf-8"))
        return [record["report"] for record in data.get("records", []) if isinstance(record.get("report"), dict)]
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="append", required=True, help="label=run_dir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    actions: dict[str, Counter] = defaultdict(Counter)
    artifacts = Counter()
    documents = 0
    for spec in args.run:
        label, run_dir = spec.split("=", 1)
        reports = load_reports(Path(run_dir).resolve())
        for report in reports:
            documents += 1
            validation = report.get("output_validation") or {}
            kind = validation.get("kind")
            artifacts[f"{label}:{kind}"] += 1
            for action in report.get("actions", []):
                stats = actions[action["action_id"]]
                stats[f"{label}:{action['status']}"] += 1
                if action.get("failure_reason"):
                    stats[f"reason:{action['failure_reason']}"] += 1
                for target in action.get("targets", []):
                    if target.get("reason"):
                        stats[f"reason:{target['reason']}"] += 1
            for edit in report.get("edit_plan", {}).get("edits", []):
                record = edit.get("verification") or {}
                actions[edit["action_id"]][f"{label}:edits"] += 1
                if record.get("passed"):
                    actions[edit["action_id"]][f"{label}:verified"] += 1
    lines = ["# FundLex 发布证据（真实运行汇总）", "",
             f"- 生成时间：{datetime.now(timezone.utc).isoformat()}",
             f"- 运行集合：{', '.join(spec.split('=')[0] for spec in args.run)}",
             f"- 合同数：{documents}",
             f"- 产物校验：{dict(artifacts)}", "",
             "| 动作 | 执行 | 验证通过 | 拒绝/未命中（原因计数） |", "| --- | --- | --- | --- |"]
    for action_id in sorted(actions):
        stats = actions[action_id]
        executed = sum(value for key, value in stats.items() if key.endswith(":edits"))
        verified = sum(value for key, value in stats.items() if key.endswith(":verified"))
        reasons = "；".join(f"{key.split('reason:')[1]}×{value}" for key, value in sorted(stats.items())
                            if key.startswith("reason:")) or "—"
        lines.append(f"| {action_id} | {executed} | {verified} | {reasons} |")
    lines += ["", "说明：本表是执行与安全证据；除 R03-A3/R04-A1/R11-A1/R10-A1 有冻结独立标签外，"
                  "其余动作没有外部业务真值，不构成准确率声明。",
                  "执行数为 0 的动作表示这些合同中未出现匹配的旧文或条件不适用（失败关闭、不修改）；"
                  "其功能由确定性动作审计覆盖（每动作至少 1 正例 + 1 反例，全部通过，见 docs/RELEASE_POLICY_V2_INTERNAL.md）。"]
    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output, "documents": documents,
                      "actions": len(actions)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
