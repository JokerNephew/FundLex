"""Shared guide-generation run creation for Web and external channels."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from ..store import NotFound, StoreError
from .store import GuideGenerationStore

ALLOWED_SUFFIXES = {".docx", ".pdf"}
MAX_REGULATION_BYTES = 80 * 1024 * 1024
MAX_PUBLIC_CONFIG_CHARS = 64 * 1024


class ArtifactIntegrityError(RuntimeError):
    """A registered artifact no longer matches its owner-visible bytes."""

    code = "ARTIFACT_INTEGRITY_MISMATCH"


# Public Web members may tune the run's business behaviour.  Transport,
# credentials, server filesystem paths and budget caps are deliberately absent:
# those are operator-only settings and must never be accepted from a request.
# Every accepted field has an explicit type and bound.  Unknown fields fail
# closed instead of being passed through to PipelineConfig (FL-D452).
_PUBLIC_INT_FIELDS: dict[str, tuple[int, int]] = {
    "corpus_limit": (1, 10000),
    "path_a_top_k": (1, 500),
    "path_a_per_contract": (1, 20),
    "path_a_max_candidates": (1, 500),
    "path_a_max_intent_calls": (0, 1000),
    "path_b_batch_chars": (2000, 100000),
    "path_b_max_requirements": (1, 100),
    "path_b_max_calls": (0, 100000),
    "path_c_max_calls": (0, 10000),
    "local_batch_size": (1, 32),
    "repair_rounds": (0, 10),
    "supplement_rounds": (0, 10),
    "max_residual_rounds": (0, 20),
    "required_clean_rounds": (1, 10),
    "residual_max_calls_per_round": (0, 10000),
}
_PUBLIC_BOOL_FIELDS = frozenset({
    "path_b_latest_only", "path_c_enabled", "adjudicate_lexical",
    "semantic_applicability", "run_engine_compatibility",
})
_PUBLIC_LIST_FIELDS = frozenset({"guide_scope_sections"})
# The public form historically sent the repository-relative corpus name.  It is
# accepted only as an alias for the server-selected corpus; the value is never
# used as a filesystem path.
_CORPUS_ALIASES = frozenset({"funds_word"})


def _server_corpus_dir() -> str:
    return os.environ.get("FUNDLEX_GUIDE_CORPUS_DIR") or str(
        Path(__file__).resolve().parent.parent.parent / "funds_word")


def sanitize_public_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Validate a member-supplied config against a strict typed allowlist.

    ``vector_*`` transport/credential/index fields, ``corpus_dir``,
    ``sample_contract`` and ``soft_max_*`` are operator configuration.  They
    are rejected even when a value looks harmless so a member cannot redirect
    embeddings, name an environment variable, read an arbitrary server file or
    change run budgets.
    """
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ValueError("CONFIG_INVALID")
    clean: dict[str, Any] = {}
    for key, value in config.items():
        if key == "corpus_dir":
            # Alias-only: the actual path is chosen by the server.  Absolute
            # paths, traversal and arbitrary relative directories are refused.
            if not isinstance(value, str) or value.strip() not in _CORPUS_ALIASES:
                raise ValueError("CONFIG_FIELD_FORBIDDEN")
            continue
        if not isinstance(key, str) or key not in (
                set(_PUBLIC_INT_FIELDS) | _PUBLIC_BOOL_FIELDS | _PUBLIC_LIST_FIELDS):
            raise ValueError("CONFIG_FIELD_FORBIDDEN")
        if key in _PUBLIC_INT_FIELDS:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("CONFIG_VALUE_INVALID")
            low, high = _PUBLIC_INT_FIELDS[key]
            if value < low or value > high:
                raise ValueError("CONFIG_VALUE_INVALID")
            clean[key] = value
        elif key in _PUBLIC_BOOL_FIELDS:
            if not isinstance(value, bool):
                raise ValueError("CONFIG_VALUE_INVALID")
            clean[key] = value
        else:
            if not isinstance(value, list) or len(value) > 50:
                raise ValueError("CONFIG_VALUE_INVALID")
            sections: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    raise ValueError("CONFIG_VALUE_INVALID")
                text = item.strip()
                if not text or len(text) > 200 or "/" in text or "\\" in text:
                    raise ValueError("CONFIG_VALUE_INVALID")
                sections.append(text)
            clean[key] = sections
    return clean


def _config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Apply server defaults after the public config allowlist.

    Feishu has no config editor and uses the same server defaults; no
    filesystem or budget value is ever accepted from a chat message.
    """
    payload = dict(config or {})
    payload.setdefault("corpus_limit", max(1, min(10000, int(
        os.environ.get("FUNDLEX_GUIDE_DEFAULT_CORPUS_LIMIT", "1")))))
    payload.setdefault("corpus_dir", os.environ.get("FUNDLEX_GUIDE_CORPUS_DIR")
                       or str(Path(__file__).resolve().parent.parent.parent / "funds_word"))
    # Cost and cumulative call totals are observation-only (2026-10-29 policy).
    # No soft cap is injected here; progress/saturation gates decide completion.
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
    public_config = sanitize_public_config(config)
    payload = _config(public_config)
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


def candidate_engine_identity(gg: GuideGenerationStore, run_id: str) -> dict[str, Any]:
    """Bind an engine-compatibility request to the current candidate bytes."""
    from .models import sha256_json

    candidate = gg.get_candidate(run_id)
    version = gg.get_candidate_version(run_id, candidate["current_version_id"])
    artifact = (version.get("payload") or {}).get("guide_artifact") or {}
    identity = {
        "candidate_version_id": version["candidate_version_id"],
        "candidate_version_no": version.get("version_no"),
        "content_sha256": version.get("content_sha256") or "",
        "guide_sha256": artifact.get("sha256") or "",
        "guide_object_key": artifact.get("object_key") or "",
        "engine_compatibility": "engine-compatibility-1",
    }
    identity["input_sha256"] = sha256_json(identity)
    return identity


def verified_artifact(gg: GuideGenerationStore, run_id: str, kind: str, *,
                      owner: str) -> dict[str, Any]:
    """Single verified accessor for guide/report downloads and Feishu.

    The owner check is part of this accessor (not only the route), the object
    path is constrained to the store root by ``RunStore.object_path``, and the
    actual bytes are re-hashed before any caller can send them.  A missing
    artifact is ``NotFound``; a corrupt/truncated one raises
    :class:`ArtifactIntegrityError` so HTTP can return a stable 409.
    """
    gg.get_run_for_owner(owner, run_id)
    artifact = gg.get_download_artifact(run_id, kind)
    if not artifact:
        raise NotFound("artifact not found")
    try:
        path = gg.store.object_path(str(artifact["object_key"]))
    except StoreError:
        raise ArtifactIntegrityError(ArtifactIntegrityError.code) from None
    if not path.is_file():
        raise NotFound("artifact not found")
    data = path.read_bytes()
    expected_size = int(artifact.get("size") or 0)
    expected_sha = str(artifact.get("sha256") or "")
    actual_sha = hashlib.sha256(data).hexdigest()
    if not expected_sha or expected_size != len(data) or expected_sha != actual_sha:
        raise ArtifactIntegrityError(ArtifactIntegrityError.code)
    return {**artifact, "path": path, "data": data, "sha256": actual_sha,
            "size": len(data)}
