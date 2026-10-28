"""Shared DOCX preparation for Compare uploads from Web and Feishu."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import hashlib

from ..upload_validation import validate_docx_upload
from .parser import parse_compare_document

try:  # Older deployments do not have the tracked-revision normalizer.
    from .revisions import prepare_compare_input
except ImportError:  # pragma: no cover - production compatibility path
    prepare_compare_input = None


def prepare_compare_upload(name: str, data: bytes) -> dict[str, Any]:
    """Validate one Compare input and accept existing tracked revisions.

    ``validate_docx_upload`` enforces the Web upload limits; the Compare parser
    additionally proves that the normalized package is readable by the worker.
    """
    filename = Path((name or "").replace("\\", "/")).name
    validate_docx_upload(filename, data)
    normalized = data
    original_sha256 = hashlib.sha256(data).hexdigest()
    revisions_accepted = 0
    if prepare_compare_input is not None:
        try:
            prepared = prepare_compare_input(data)
            normalized = prepared.data
            original_sha256 = prepared.original_sha256
            revisions_accepted = prepared.revisions_accepted
        except Exception as exc:
            raise ValueError("COMPARE_INVALID_DOCX") from exc
    try:
        parse_compare_document(normalized, filename=filename)
    except Exception as exc:
        raise ValueError("COMPARE_INVALID_DOCX") from exc
    return {"data": normalized, "original_sha256": original_sha256,
            "original_size": len(data), "revisions_accepted": revisions_accepted}
