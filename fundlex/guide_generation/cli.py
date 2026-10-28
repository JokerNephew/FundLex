"""Command line entry points for guide generation and offline evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from ..store import RunStore
from .corpus_catalog import sync_corpus
from .model_router import GuideModelRouter
from .pipeline import GuidePipeline, PipelineConfig
from .store import GuideGenerationStore
from .worker import GuideGenerationWorker


def _store(args) -> RunStore:
    data_dir = args.data_dir or os.environ.get("FUNDLEX_DATA_DIR") or str(Path.home() / ".local/share/fundlex")
    return RunStore(data_dir)


def cmd_sync_corpus(args) -> int:
    store = _store(args)
    gg = GuideGenerationStore(store)
    result = sync_corpus(gg, args.corpus_dir, limit=args.limit, force=args.force)
    print(json.dumps({"snapshot": result.snapshot.to_dict(), "parsed": result.parsed,
                      "reused": result.reused, "skipped": result.skipped,
                      "errors": result.errors[:20]}, ensure_ascii=False, indent=2))
    return 0


def cmd_create_run(args) -> int:
    store = _store(args)
    gg = GuideGenerationStore(store)
    gg.ensure_schema()
    source = Path(args.file)
    data = source.read_bytes()
    suffix = source.suffix.lower()
    if suffix not in {".docx", ".pdf"}:
        raise SystemExit("only DOCX/PDF regulations are supported")
    digest = hashlib.sha256(data).hexdigest()
    config = json.loads(args.config_json or "{}")
    config.setdefault("corpus_dir", args.corpus_dir or os.environ.get("FUNDLEX_GUIDE_CORPUS_DIR", "funds_word"))
    run = gg.create_run(owner=args.owner, filename=source.name, source_type=suffix[1:],
                        source_sha256=digest, title=source.stem,
                        payload={"config": config, "source_sha256": digest})
    relpath = f"guide_generation/{run['id']}/source{suffix}"
    target = store.object_path(relpath)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    gg.update_run(run["id"], payload={**(run.get("payload") or {}), "source_relpath": relpath,
                                      "source_object_key": relpath, "source_size": len(data)})
    gg.enqueue(run["id"])
    print(run["id"])
    return 0


def cmd_run(args) -> int:
    store = _store(args)
    gg = GuideGenerationStore(store)
    run = gg.get_run(args.run_id)
    payload = run.get("payload") or {}
    config = PipelineConfig.from_payload(payload.get("config") or {}, args.corpus_dir or "")
    if args.no_residual:
        config.max_residual_rounds = 0
    if args.no_semantic:
        config.semantic_applicability = False
    if args.corpus_limit is not None:
        config.corpus_limit = args.corpus_limit
    if args.latest_only:
        config.path_b_latest_only = True
    router = GuideModelRouter.from_env()
    try:
        result = GuidePipeline(gg, args.run_id, router, config).run()
        print(json.dumps({"id": result["id"], "status": result["status"],
                          "stage": result.get("stage"),
                          "qualification_status": result.get("qualification_status"),
                          "stats": gg.stats(args.run_id)}, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"complete", "complete_with_unresolved", "completed"} else 1
    finally:
        router.close()


def cmd_worker(args) -> int:
    store = _store(args)
    worker = GuideGenerationWorker(store, lease_seconds=args.lease_seconds)
    if args.once:
        worker.run_once()
    else:
        worker.run_forever(poll_seconds=args.poll)
    return 0


def cmd_benchmark(args) -> int:
    from .benchmark import score_run, summary_text
    data_dir = args.data_dir or os.environ.get("FUNDLEX_DATA_DIR") or str(Path.home() / ".local/share/fundlex")
    store = RunStore(data_dir, read_only=True)
    gg = GuideGenerationStore(store, read_only=True)
    result = score_run(gg, args.run_id, args.gold)
    print(summary_text(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FundLex regulation-driven guide generation")
    parser.add_argument("--data-dir", default="")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sync-corpus")
    p.add_argument("--corpus-dir", default=os.environ.get("FUNDLEX_GUIDE_CORPUS_DIR", "funds_word"))
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_sync_corpus)

    p = sub.add_parser("create-run")
    p.add_argument("--owner", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--corpus-dir", default="")
    p.add_argument("--config-json", default="{}")
    p.set_defaults(func=cmd_create_run)

    p = sub.add_parser("run")
    p.add_argument("--run-id", required=True)
    p.add_argument("--corpus-dir", default="")
    p.add_argument("--corpus-limit", type=int, default=None)
    p.add_argument("--latest-only", action="store_true")
    p.add_argument("--no-residual", action="store_true")
    p.add_argument("--no-semantic", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("worker")
    p.add_argument("--once", action="store_true")
    p.add_argument("--poll", type=float, default=2.0)
    p.add_argument("--lease-seconds", type=int, default=3600)
    p.set_defaults(func=cmd_worker)

    p = sub.add_parser("benchmark")
    p.add_argument("--run-id", required=True)
    p.add_argument("--gold", default="benchmarks/sales_fee_regulation_2025/gold.json")
    p.set_defaults(func=cmd_benchmark)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
