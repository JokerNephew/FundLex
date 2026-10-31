#!/usr/bin/env python3
"""Prepare (but NOT launch) the wave-2 engine run directory.

Mirrors the wave-1 convention:
``var/recall-first-evaluation/qa-wave2-<split>-<date>-<head8>/`` containing
``selection…json`` copy, labels copy, ``freeze.json``, ``inputs_flat/``,
``load_env.sh`` (sudo-read of /etc/fundlex-recall.env, never prints values) and
``run_full.sh`` gated on ``FUNDLEX_WAVE2_GATE=ALLOW`` (mainline放行令).

This script never runs the engine and never touches the holdout corpus beyond
copying the frozen files listed in the frozen selection manifest.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "var/recall-first-evaluation"

LOAD_ENV = r"""#!/usr/bin/env bash
# Safely load model env (LLM_* / FUNDLEX_MODEL_*) from /etc/fundlex-recall.env.
# Values are never printed or expanded into command arguments.
EXPORTS=$(sudo -n python3 - <<'PYEOF'
import shlex
for raw in open('/etc/fundlex-recall.env', encoding='utf-8'):
    line = raw.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    if line.startswith('export '):
        line = line[7:].lstrip()
    key, _, val = line.partition('=')
    key = key.strip()
    if key.startswith('LLM_') or key.startswith('FUNDLEX_MODEL_'):
        print(f'export {key}={shlex.quote(val.strip())}')
PYEOF
) || { echo "load_env: sudo python3 failed" >&2; return 1; }
eval "$EXPORTS"
unset EXPORTS
export FUNDLEX_MODEL_ENFORCE_LIMITS=0
"""

RUN_FULL = r"""#!/usr/bin/env bash
# QA wave2 {SPLIT} full run launcher (frozen inputs; see freeze.json in this dir).
# GATED: refuse to start until the mainline放行令 arrives (FUNDLEX_WAVE2_GATE=ALLOW).
set -u
[ "${{FUNDLEX_WAVE2_GATE:-}}" = "ALLOW" ] || {{ echo "gated: wave2 engine run blocked pending mainline放行令" >&2; exit 2; }}
cd {ROOT}
WAVE={WAVE}

source "$WAVE/load_env.sh"
python3 -c 'import os,json;json.loads(os.environ["FUNDLEX_MODEL_REQUEST_OPTIONS_JSON"]);json.loads(os.environ["FUNDLEX_MODEL_EXTRA_HEADERS_JSON"])' \
  || {{ echo "env JSON invalid" >&2; exit 1; }}

exec .venv/bin/python -X utf8 -m tools.evaluation.recall_run \
  --input "$WAVE/inputs_flat" \
  --output "$WAVE/full" \
  --max-calls {MAX_CALLS} --max-cost-usd 1000000 \
  --ledger "$WAVE/ledger.sqlite" \
  --resume
"""

README = """# QA wave2 {SPLIT} run directory (SCAFFOLD, gated)

Created by `tools/evaluation/prepare_second_batch_run_20261031.py` on {CREATED}.
State: **prepared, engine NOT run**. 主线放行令（dev20 v2 达标后）到达后：

1. 复核 `freeze.json` 与当下引擎 HEAD/guide/labels/selection 漂移；若有漂移，新建 run 目录而不是覆盖本目录。
2. `FUNDLEX_WAVE2_GATE=ALLOW bash run_full.sh`（脚本自带闸门）。
3. 运行后评分：`score.json` 链路沿用 wave-1 评分工位（labels 冻结 sha 见 freeze.json）。

Do not edit anything in this directory by hand; keep the freeze intact.
"""


def sha256_file(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "holdout"], required=True)
    ap.add_argument("--selection", default="docs/evidence/selection-second-batch-20261031.json")
    ap.add_argument("--labels", default="docs/evidence/labels-second-batch-20261031-v1.json")
    ap.add_argument("--verification", default="docs/evidence/labels-second-batch-20261031-v1-verification.json")
    ap.add_argument("--guide", default="guides/builtin_guide_v1.json")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--write", action="store_true", help="materialize (default: dry-run)")
    args = ap.parse_args()

    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    sel_cases = {c["case_id"]: c for c in selection["cases"]}
    prefix = "W2D" if args.split == "dev" else "W2H"
    wanted = [c for c in labels["cases"] if c["case_id"].startswith(prefix)]

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    run_id = args.run_id or f"qa-wave2-{args.split}-20261031-{head[:8]}"
    wave = RUNS / run_id

    print(f"[prepare] run dir: {wave}")
    print(f"[prepare] cases: {len(wanted)} ({args.split}); engine head {head[:8]} branch {branch}")
    if not args.write:
        print("[prepare] dry-run — pass --write to materialize")
        return 0
    if wave.exists():
        print(f"[prepare] refuse to overwrite existing run dir {wave}; use --run-id for a new one", file=sys.stderr)
        return 2

    (wave / "inputs_flat").mkdir(parents=True)
    shutil.copy2(args.selection, wave / Path(args.selection).name)
    shutil.copy2(args.labels, wave / Path(args.labels).name)
    shutil.copy2(args.verification, wave / Path(args.verification).name)
    src_root = Path(selection["source_root"])
    copied = 0
    for case in wanted:
        src = src_root / case["file"]
        if not src.exists():
            print(f"[prepare] MISSING source {src}", file=sys.stderr)
            return 2
        selc = sel_cases[case["case_id"]]
        if sha256_file(src) != selc["sha256"]:
            print(f"[prepare] source drift for {case['case_id']}: {src}", file=sys.stderr)
            return 2
        shutil.copy2(src, wave / "inputs_flat" / case["file"])
        copied += 1
    freeze = {
        "schema": "fundlex-qa-wave2-freeze-v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "wave": "second-batch-20261031",
        "split": args.split,
        "gate": "FUNDLEX_WAVE2_GATE=ALLOW required (mainline放行令)",
        "engine_head": head,
        "engine_branch": branch,
        "engine_workspace_uncommitted": [line for line in dirty if "node_modules" not in line],
        "guide": {"path": args.guide, "sha256": sha256_file(ROOT / args.guide)},
        "labels": {"path": args.labels, "sha256": sha256_file(ROOT / args.labels)},
        "labels_verification": {"path": args.verification, "sha256": sha256_file(ROOT / args.verification)},
        "selection": {"path": args.selection, "sha256": sha256_file(ROOT / args.selection)},
        "model": {"provider": "hon-maas", "model": "kimi-k3 (engine family; concrete deployment version to be re-frozen at run time)"},
        "scoring": {"labels_schema": "docs/evidence/labels-schema-second-batch-20261031-v1.md"},
    }
    (wave / "freeze.json").write_text(json.dumps(freeze, ensure_ascii=False, indent=1), encoding="utf-8")
    (wave / "load_env.sh").write_text(LOAD_ENV, encoding="utf-8")
    run_sh = RUN_FULL.format(SPLIT=args.split, ROOT=ROOT, WAVE=wave, MAX_CALLS=10 * len(wanted))
    (wave / "run_full.sh").write_text(run_sh, encoding="utf-8")
    (wave / "README.md").write_text(README.format(SPLIT=args.split, CREATED=freeze["frozen_at"]), encoding="utf-8")
    print(f"[prepare] wrote {wave} (inputs {copied}, freeze sha self-check ok)")
    print(f"[prepare] run stays gated; launch only after mainline放行令: FUNDLEX_WAVE2_GATE=ALLOW bash {wave}/run_full.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
