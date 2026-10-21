"""Zero-network D01 replay probe; changes only in-memory validator references."""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
import traceback
from pathlib import Path


REPO = Path.cwd()
ROOT = REPO / "docs/evidence/final-validation-20261022"
OUT = ROOT / "diagnostics/D01-validate-plan-capture.json"
sys.path.insert(0, str(REPO))

import httpx

network_attempts = []


def forbidden(*args, **kwargs):
    network_attempts.append("HTTP_SEND_ATTEMPT")
    raise AssertionError("REPLAY_NETWORK_FORBIDDEN")


httpx.Client.send = forbidden
httpx.AsyncClient.send = forbidden

import fundlex.docx as docx
import fundlex.recall_pipeline as pipeline

real_validate = docx.validate_edit_plan
captures = []


def save():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "case_id": "D01", "mode": "replay", "network_attempts": network_attempts,
        "validator_calls": captures,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def probe(source, edits, templates, **kwargs):
    snapshot = [dict(edit) for edit in edits]
    pairs = []
    for i, edit in enumerate(snapshot):
        for j, previous in enumerate(snapshot[:i]):
            if edit.get("location") == previous.get("location") and not (
                edit["end"] < previous["start"] or edit["start"] > previous["end"]
            ):
                pairs.append({"incoming_index": i, "previous_index": j,
                              "location": edit.get("location"),
                              "incoming_range": [edit["start"], edit["end"]],
                              "previous_range": [previous["start"], previous["end"]]})
    capture = {"call_index": len(captures), "source": str(source),
               "incoming_edits": snapshot, "overlap_or_adjacency_pairs": pairs,
               "stack": traceback.format_stack()}
    captures.append(capture)
    try:
        result = real_validate(source, edits, templates, **kwargs)
    except Exception as exc:
        capture["result"] = "ERROR"
        capture["error_code"] = getattr(exc, "code", str(exc))
        capture["exception_stack"] = traceback.format_exc()
        save()
        raise
    capture["result"] = "PASS"
    save()
    return result


docx.validate_edit_plan = probe
pipeline.validate_edit_plan = probe
sys.argv = [str(REPO / "tools/validate_frozen_case.py"), "D01", "replay", "--root", str(ROOT)]
try:
    runpy.run_path(str(REPO / "tools/validate_frozen_case.py"), run_name="__main__")
finally:
    save()
