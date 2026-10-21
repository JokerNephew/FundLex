"""Run one real-model subset case with production credentials (root-only env file)."""
from __future__ import annotations

import json
import os
import pathlib
import sys

REPO = pathlib.Path("/home/opencode/fundlex")
sys.path.insert(0, str(REPO))

CASES = {
    "D01": "广发上海清算所0-4年央企80债券指数证券投资基金基金合同_20250319.docx",
    "D02": "广发上证50交易型开放式指数证券投资基金发起式联接基金基金合同_20241113.docx",
    "D11": "广发景和中短债债券型证券投资基金基金合同_20240122.docx",
    "D16": "广发瑞福精选混合型证券投资基金基金合同_20260626.docx",
}
SAMPLES = pathlib.Path("/home/opencode/data/funds_word")


def load_env(path: str = "/etc/fundlex-recall.env") -> None:
    for raw in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        os.environ[key] = value


def main() -> int:
    case = sys.argv[1]
    output = pathlib.Path(sys.argv[2])
    ledger = output / "ledger.sqlite"
    output.mkdir(parents=True, exist_ok=True)
    load_env()
    os.environ["FUNDLEX_GENERATION_STRATEGY"] = "registry"
    os.environ["FUNDLEX_MODEL_LEDGER"] = str(ledger)
    os.environ["FUNDLEX_MODEL_MAX_CALLS"] = "200"
    os.environ["FUNDLEX_MODEL_MAX_REQUESTS"] = "200"
    os.environ["FUNDLEX_MODEL_MAX_COST_USD"] = "0.6"
    os.environ.setdefault("FUNDLEX_MODEL_CONCURRENCY", "1")
    os.environ.setdefault("FUNDLEX_MODEL_INPUT_USD_PER_M", "0.15")
    os.environ.setdefault("FUNDLEX_MODEL_OUTPUT_USD_PER_M", "0.6")
    from tools.evaluation import recall_run

    return recall_run.main([
        "--input", str(SAMPLES / CASES[case]),
        "--output", str(output),
        "--ledger", str(ledger),
        "--max-calls", "200",
        "--max-cost-usd", "0.6",
        "--business-rounds", "3",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
