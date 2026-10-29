#!/usr/bin/env python3
"""Map direct recall-run outputs to the first-batch label case IDs and score.

The engine's library-level runner writes directories such as
``001-<contract stem>``.  The evaluator labels use ``B01``/``BH01``.  This
adapter only links the actual artifacts into a case-ID run tree; it never
rewrites a DOCX or report.  The real score is produced by ``p6_score``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION = ROOT / "var/recall-first-evaluation/first-batch-20261028/selection-first-batch-20261028.json"
DEFAULT_LABELS = ROOT / "docs/evidence/labels-first-batch-20261028-v2.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="direct recall-run output")
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--group", choices=("dev", "holdout", "all"), default="dev")
    parser.add_argument("--mapped", type=Path, required=True,
                        help="directory containing case-ID linked artifacts")
    parser.add_argument("--output", type=Path,
                        help="score JSON (default: <mapped>/score.json)")
    args = parser.parse_args(argv)

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    wanted = [case for case in selection["cases"]
              if args.group == "all" or case["group"] == args.group]
    if not wanted:
        raise SystemExit("selection has no cases in the requested group")

    # Recall-run output directories carry a numeric prefix; match by the source
    # filename/stem.  Hash matching is not relied on because a stopped report can
    # have an empty source hash.
    directories = [path for path in args.run.iterdir()
                   if path.is_dir() and (path / "report.json").is_file()]
    by_stem = {}
    for directory in directories:
        stem = directory.name.split("-", 1)[-1]
        by_stem.setdefault(stem, directory)

    args.mapped.mkdir(parents=True, exist_ok=True)
    mapped_ids = []
    missing = []
    for case in wanted:
        case_id = case["case_id"]
        name = case["file"]
        source_stem = Path(name).stem
        source = by_stem.get(source_stem)
        if source is None:
            # Long stems are truncated by recall_run at 40 characters.
            matches = [path for stem, path in by_stem.items()
                       if source_stem.startswith(stem) or stem.startswith(source_stem[:40])]
            source = matches[0] if len(matches) == 1 else None
        target = args.mapped / case_id
        target.mkdir(parents=True, exist_ok=True)
        if source is None:
            missing.append(case_id)
            continue
        for name, dest in (("final.docx", "final.docx"),
                           ("redline.docx", "redline.docx"),
                           ("report.json", "report.json")):
            src = source / name
            if src.is_file():
                dst = target / dest
                if dst.exists():
                    dst.unlink()
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
        if (target / "report.json").is_file():
            mapped_ids.append(case_id)
        else:
            missing.append(case_id)
    (args.mapped / "batch.json").write_text(
        json.dumps({"cases": mapped_ids}, ensure_ascii=False) + "\n", encoding="utf-8")
    if missing:
        print("unmapped cases:", ",".join(missing), file=sys.stderr)
    output = args.output or args.mapped / "score.json"
    command = [sys.executable, "-m", "tools.evaluation.p6_score",
               "--labels", str(args.labels), "--run", str(args.mapped),
               "--group", args.group, "--output", str(output)]
    subprocess.run(command, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
