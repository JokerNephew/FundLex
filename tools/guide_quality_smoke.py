"""Deterministic footprint smoke for an already-parsed guide version.

Compares the version's rule footprint against its lineage baseline (parent
re-parse version, or the built-in guide when the uploaded source hashes equal
the built-in source) and stamps/clears the advisory ``needs_review`` verdict.
No model is called.  Exit 0 when the footprint is healthy or there is no
baseline; exit 1 when a regression was found and marked.

Run from the repository root:

    .venv/bin/python -m tools.guide_quality_smoke --data-dir var/state \
        --owner <owner> --version-id <id>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fundlex.guide_smoke import review_version_footprint
from fundlex.store import RunStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, help="RunStore state directory")
    parser.add_argument("--owner", required=True, help="guide version owner")
    parser.add_argument("--version-id", required=True)
    args = parser.parse_args(argv)
    if not Path(args.data_dir).is_dir():
        print(json.dumps({"error": f"DATA_DIR_MISSING:{args.data_dir}"}, ensure_ascii=False))
        return 2
    store = RunStore(args.data_dir)
    try:
        result = review_version_footprint(store, args.owner, args.version_id)
    except KeyError:
        print(json.dumps({"error": "GUIDE_VERSION_NOT_FOUND"}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("needs_review") else 0


if __name__ == "__main__":
    sys.exit(main())
