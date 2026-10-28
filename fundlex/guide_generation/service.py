"""Shared guide-generation run creation for Web and external channels."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

ALLOWED_SUFFIXES = {".docx", ".pdf"}
MAX_REGULATION_BYTES = 80 * 1024 * 1024


def _config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Apply the same conservative server defaults as the public Web API.

    The Web route validates a narrower public config model. Feishu has no config
    editor, so it uses server defaults and never accepts filesystem or budget
    values from the chat.
    """
    payload = dict(config or {})
    payload.setdefault("corpus_limit", max(1, min(10000, int(
        os.environ.get("FUNDLEX_GUIDE_DEFAULT_CORPUS_LIMIT", "1")))))
    payload.setdefault("corpus_dir", os.environ.get("FUNDLEX_GUIDE_CORPUS_DIR")
                       or str(Path(__file__).resolve().parent.parent.parent / "funds_word"))
    payload.setdefault("soft_max_calls", int(os.environ.get("FUNDLEX_GUIDE_RUN_MAX_CALLS", "6000")))
    payload.setdefault("soft_max_cost", float(os.environ.get("FUNDLEX_GUIDE_RUN_MAX_COST_USD", "12")))
    return payload


def create_run(store, gg, owner: str, filename: str, data: bytes,
               config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create and enqueue one regulation run.

    Validation errors use stable codes so the HTTP and Feishu adapters can map
    them without duplicating business rules.
    """
    safe_name = Path((filename or "").replace("\\", "/")).name.strip()
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("REGULATION_TYPE_UNSUPPORTED")
    if not data:
        raise ValueError("REGULATION_EMPTY")
    if len(data) > MAX_REGULATION_BYTES:
        raise ValueError("REGULATION_FILE_LIMIT")
    payload = _config(config)
    digest = hashlib.sha256(data).hexdigest()
    run = gg.create_run(owner=owner, filename=safe_name, source_type=suffix[1:],
                        source_sha256=digest, title=Path(safe_name).stem,
                        payload={"config": payload, "source_sha256": digest,
                                 "uploaded_filename": safe_name})
    relpath = f"guide_generation/{run['id']}/source{suffix}"
    target = store.object_path(relpath)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    gg.update_run(run["id"], payload={**(run.get("payload") or {}),
                                      "source_relpath": relpath,
                                      "source_object_key": relpath,
                                      "source_size": len(data)})
    gg.enqueue(run["id"])
    return gg.get_run(run["id"])
