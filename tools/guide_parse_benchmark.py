"""Guide parse quality benchmark (real model, ledgered; FL-D445 observability).

Runs the production parse channel against the two maintained guide documents
and scores the CHANNEL deterministically — never the model's self-assessment:

* fee-rule v4 (errata): the channel must end either certified AND canary-pass
  (executable, enableable) or blocked with structured reasons; the gate
  slipping a non-executable parse through is a benchmark failure (FL-D648).
* fee-rule V2: known host with a source typo and branch ambiguity; the
  channel must NOT certify it silently — structured validation errors,
  verifier findings or a canary review must be on record.

Optional ``--engine-smoke N`` executes the recall engine (real production
path: TestClient → task → upload → Worker.run_once) over N pairs from
references/fee-rule-v2 (33 golden contracts) for both the built-in guide and
the freshly parsed one when it certifies, printing delivery/target verdicts.
Width N stays small by default; full-corpus runs belong to the eval wave.

Usage (repo root, LLM_* env present):

    .venv/bin/python -m tools.guide_parse_benchmark --guides v4 v2 \
        --ledger /tmp/opencode/guide-parse-benchmark.sqlite --max-calls 40 \
        --out /tmp/opencode/guide-parse-benchmark.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

GUIDES = {
    "v4": ("references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx",
           {"expect": "certify_or_structured_block"}),
    "v2": ("references/source/存量基金适用销售费用新规的基金合同修改指引V2.docx",
           {"expect": "structured_block"}),
}


def configure(args: argparse.Namespace) -> None:
    os.environ["FUNDLEX_MODEL_LEDGER"] = str(Path(args.ledger).resolve())
    os.environ["FUNDLEX_MODEL_MAX_CALLS"] = str(args.max_calls)
    os.environ["FUNDLEX_MODEL_MAX_REQUESTS"] = str(args.max_calls)


def run_parse(guide_path: Path) -> dict:
    from fundlex.guide import GuideError, build_guide_document, extract_guide_source
    from fundlex.model import ModelGateway
    source = extract_guide_source(guide_path)
    try:
        document = build_guide_document(source, ModelGateway.from_env(),
                                        max_repair_rounds=2)
    except GuideError as exc:
        return {"source_sha256": source.source_sha256, "paragraphs": len(source.paragraphs),
                "error_code": exc.code, "details": exc.details}
    validation = document.get("validation") or {}
    from fundlex.guide_canary import executability_report
    canary = executability_report(document)
    return {"source_sha256": source.source_sha256,
            "paragraphs": len(source.paragraphs),
            "rules": len(document.get("groups") or []),
            "clean": bool(validation.get("clean")),
            "errors": [str(e.get("code")) for e in validation.get("errors") or []],
            "coverage_gaps": len(validation.get("coverage_gaps") or []),
            "findings": len((validation.get("verification") or {}).get("findings") or []),
            "invalid_findings": (validation.get("verification") or {}).get("invalid_findings"),
            "rounds": validation.get("rounds"),
            "canary": {"passed": canary["passed"],
                       "executable_ratio": canary["executable_ratio"],
                       "fatal_codes": sorted({f["code"] for f in canary["fatal"]}),
                       "blocking_gaps": canary["blocking_gaps"]},
            "document": document}


def score_channel(result: dict, expect: str) -> dict:
    """Deterministic channel verdict."""
    if result.get("error_code"):
        return {"verdict": "blocked_transport", "ok": expect == "structured_block",
                "reason": result["error_code"]}
    clean = bool(result.get("clean"))
    canary_passed = result["canary"]["passed"]
    structured = bool(result.get("errors") or result.get("coverage_gaps")
                      or result.get("findings") or result.get("invalid_findings"))
    if clean and canary_passed:
        verdict, ok = "certified_executable", expect == "certify_or_structured_block"
    elif clean and not canary_passed:
        verdict, ok = "gate_caught_nonexecutable", True
    elif not clean and structured:
        verdict, ok = "blocked_structured", True
    else:
        verdict, ok = "channel_failure", False
    return {"verdict": verdict, "ok": ok,
            "expect": expect, "clean": clean, "canary_passed": canary_passed}


def engine_smoke(guide_document: dict | None, count: int, out_dir: Path) -> list[dict]:
    originals = sorted((REPO / "references/fee-rule-v2/original").glob("*.docx"))[:count]
    rows: list[dict] = []
    # Real store + TestClient production path (same lane as qa-f2-guide-history).
    from fastapi.testclient import TestClient

    from fundlex import guide_store
    from fundlex.api import create_app
    from fundlex.jobs import Worker
    from fundlex.store import RunStore

    for mode, document in (("builtin", None), ("parsed", guide_document)):
        if mode == "parsed" and document is None:
            continue
        for contract in originals:
            store_dir = out_dir / f"{mode}-{contract.stem[:12]}" / "state"
            store = RunStore(store_dir)
            guide_store.ensure_builtin_guide(store)
            if document is not None:
                version = guide_store.create_custom_version(
                    store, "qa", contract.name, contract.read_bytes())
                job = guide_store.claim_guide_job(store)
                finished = guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                                        document=document)
                if finished["version"]["qualification_status"] != guide_store.QUALIFICATION_CERTIFIED:
                    rows.append({"mode": mode, "contract": contract.name, "verdict": "not_certified"})
                    continue
                try:
                    guide_store.set_current_guide(store, "qa", version["id"])
                except ValueError as exc:
                    rows.append({"mode": mode, "contract": contract.name,
                                 "verdict": f"enable_blocked:{exc}"})
                    continue
            client = TestClient(create_app(store_dir))
            data = contract.read_bytes()
            created = client.post("/api/tasks",
                                  headers={"X-FundLex-User": "qa",
                                           "Idempotency-Key": f"bench-{mode}-{contract.stem[:8]}"},
                                  json={"name": f"bench-{mode}", "engine_id": "recall_first",
                                        "files": [{"client_id": "c1", "name": contract.name,
                                                   "size": len(data)}]})
            if created.status_code != 201:
                rows.append({"mode": mode, "contract": contract.name,
                             "verdict": f"task_create_{created.status_code}"})
                continue
            task = created.json()
            client.post(f"/api/tasks/{task['id']}/uploads",
                        headers={"X-FundLex-User": "qa"},
                        data={"client_ids": json.dumps(["c1"])},
                        files=[("files", (contract.name, data))])
            Worker(store).run_once()
            items = client.get(f"/api/tasks/{task['id']}/documents",
                               headers={"X-FundLex-User": "qa"}).json()["items"]
            item = items[0]
            rows.append({"mode": mode, "contract": contract.name,
                         "delivery_status": item.get("delivery_status"),
                         "target_counts": item.get("target_counts")})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--guides", nargs="+", default=["v4", "v2"], choices=sorted(GUIDES))
    parser.add_argument("--ledger", default="/tmp/opencode/guide-parse-benchmark.sqlite")
    parser.add_argument("--max-calls", type=int, default=40,
                        help="anti-runaway guard only (FL-D445: not a budget gate)")
    parser.add_argument("--engine-smoke", type=int, default=0, metavar="N",
                        help="run the real recall engine over N golden contracts per guide variant")
    parser.add_argument("--out", default="/tmp/opencode/guide-parse-benchmark.json")
    args = parser.parse_args()
    configure(args)

    report: dict = {"benchmark": "guide-parse-quality", "guides": {}, "engine_smoke": []}
    overall_ok = True
    parsed_v4: dict | None = None
    for name in args.guides:
        path, meta = GUIDES[name]
        source_path = REPO / path
        print(f"[benchmark] parsing {name}: {source_path.name}", flush=True)
        result = run_parse(source_path)
        score = score_channel(result, meta["expect"])
        overall_ok &= bool(score["ok"])
        if name == "v4" and result.get("clean") and result.get("canary", {}).get("passed"):
            parsed_v4 = result.get("document")
        report["guides"][name] = {key: value for key, value in result.items() if key != "document"}
        report["guides"][name]["channel"] = score
        print(f"[benchmark] {name}: {json.dumps(score, ensure_ascii=False)}", flush=True)
    if args.engine_smoke > 0:
        smoke_dir = Path(tempfile.mkdtemp(prefix="guide-bench-smoke-"))
        report["engine_smoke"] = engine_smoke(parsed_v4, args.engine_smoke, smoke_dir)
        print(f"[benchmark] engine smoke rows: {len(report['engine_smoke'])} (parsed guide: "
              f"{'certified' if parsed_v4 else 'not available'})", flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[benchmark] report: {out}; overall_ok={overall_ok}", flush=True)
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
