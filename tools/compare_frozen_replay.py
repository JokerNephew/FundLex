"""Compare business state from a live recording and a zero-network full replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compare(root: Path, case: str) -> dict:
    recorded = json.loads((root / 'artifacts' / case / 'report.json').read_text())
    replayed = json.loads((root / 'replay' / case / 'report.json').read_text())
    fields = ('facts', 'scope_mapping', 'targets', 'target_attribution', 'obligations',
              'plan', 'artifact_claim_replay', 'delivery_status', 'unresolved',
              'recovery', 'audit_recovery')
    checks = {name: recorded.get(name) == replayed.get(name) for name in fields}
    attempts = replayed.get('model', {}).get('http_attempts')
    checks['zero_http_attempts'] = attempts == 0
    checks['no_replay_error'] = not replayed.get('errors') and not replayed.get('validation_stop')
    # DOCX zip metadata and revision timestamps may differ. Compare actual paragraph
    # text, never file hashes, to establish semantic reproducibility of the artifact.
    from fundlex.docx import inspect_docx
    paths = [root / mode / case / 'working_final.docx' for mode in ('artifacts', 'replay')]
    checks['artifact_text'] = all(path.is_file() for path in paths) and (
        [(p.location, p.text) for p in inspect_docx(paths[0], full=True).paragraphs] ==
        [(p.location, p.text) for p in inspect_docx(paths[1], full=True).paragraphs])
    return {'case_id': case, 'passed': all(checks.values()), 'checks': checks,
            'http_attempts': attempts}


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('cases', nargs='+')
    args = parser.parse_args()
    results = [compare(args.root, case) for case in args.cases]
    output = args.root / 'summaries' / 'full-replay-comparison.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(result['passed'] for result in results) else 1)
