#!/usr/bin/env python
"""Print one frozen FundLex stage without network or model calls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fundlex.stage_replay import STAGES, replay_stage

parser = argparse.ArgumentParser()
parser.add_argument("run_dir")
parser.add_argument("stage", choices=STAGES)
parser.add_argument("--revision", type=int, default=0)
args = parser.parse_args()
try:
    print(json.dumps(replay_stage(args.run_dir, args.stage, revision=args.revision), ensure_ascii=False, indent=2))
except Exception as exc:  # deterministic machine-readable failure
    print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(2)
