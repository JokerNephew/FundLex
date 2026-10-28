"""Run the real user processing path on a small public-contract batch.

The model environment is read only into this process.  No secret value is printed or
written to the evidence directory.  Contract names are CLI inputs so this runner cannot
silently special-case a fixture filename.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO / "funds_word" / "基金合同第一批"


def load_model_env() -> None:
    raw = subprocess.check_output(["sudo", "-n", "cat", "/etc/fundlex-recall.env"], text=True)
    prefixes = ("LLM_", "FUNDLEX_MODEL_", "FUNDLEX_PRIMARY_", "FUNDLEX_REVIEW_")
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().removeprefix("export ")
        if name.startswith(prefixes):
            os.environ[name] = value.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    load_model_env()
    os.environ.update(
        FUNDLEX_MODEL_MODE="live",
        FUNDLEX_MODEL_LEDGER=str(args.ledger),
        FUNDLEX_MODEL_MAX_REQUESTS=os.environ.get("FUNDLEX_E2E_MAX_REQUESTS", "600"),
        FUNDLEX_MODEL_MAX_COST_USD=os.environ.get("FUNDLEX_E2E_MAX_COST_USD", "2.0"),
        FUNDLEX_GENERATION_STRATEGY="registry",
    )
    from fundlex.models.roles import build_role_gateway
    from fundlex.recall_pipeline import process_recall_first

    guide = json.loads((REPO / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))
    rows = []
    gateway = build_role_gateway()
    try:
        for name in args.files:
            source = SOURCE_ROOT / name
            if not source.is_file():
                raise SystemExit(f"REAL_CONTRACT_NOT_FOUND:{name}")
            case_id = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
            out = args.output / case_id
            report = process_recall_first(source, out, guide_document=guide, gateway=gateway)
            rows.append({
                "case_id": case_id,
                "file": name,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "delivery_status": report.get("delivery_status"),
                "artifacts": report.get("artifacts"),
                "unresolved_count": len(report.get("unresolved") or []),
                "true_obligations": sum(
                    (item.get("applicability") or {}).get("status") == "TRUE"
                    for item in (report.get("obligations") or {}).get("records") or []),
                "completion_counts": (report.get("obligations") or {}).get("counts"),
                "final_omission_review": report.get("final_omission_review"),
                "operation_coverage": report.get("operation_coverage"),
                "model": report.get("model"),
            })
            (out / "batch-summary.json").write_text(
                json.dumps(rows[-1], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    finally:
        gateway.close()
    (args.output / "index.json").write_text(
        json.dumps({"contracts": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
