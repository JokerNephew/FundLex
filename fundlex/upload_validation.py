"""Shared, bounded DOCX upload validation for every task ingress."""
from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path

from lxml import etree

from .docx import REVISION_TAGS, W

MAX_UPLOAD_BYTES = int(os.environ.get("FUNDLEX_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_UNCOMPRESSED_BYTES = int(os.environ.get("FUNDLEX_MAX_UNCOMPRESSED_BYTES", str(200 * 1024 * 1024)))
MAX_BATCH_BYTES = int(os.environ.get("FUNDLEX_MAX_BATCH_BYTES", str(50 * 1024 * 1024)))
MAX_PART_BYTES = int(os.environ.get("FUNDLEX_MAX_PART_BYTES", str(32 * 1024 * 1024)))
MAX_COMPRESSION_RATIO = int(os.environ.get("FUNDLEX_MAX_COMPRESSION_RATIO", "100"))
LEGACY_DOC_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class UploadValidationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 415):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def validate_docx_upload(name: str, data: bytes) -> str:
    """Validate one DOCX using the same limits as the Web task API."""
    safe_name = Path((name or "").replace("\\", "/")).name
    suffix = Path(safe_name).suffix.lower()
    if suffix == ".doc" or data.startswith(LEGACY_DOC_MAGIC):
        # Legacy binary Word files must be saved as DOCX by the user.  Do not
        # rename them or feed them into the OOXML pipeline.
        raise UploadValidationError(
            "LEGACY_DOC_UNSUPPORTED",
            "legacy Word .doc is unsupported; save it as .docx and upload again")
    if not safe_name or suffix != ".docx":
        raise UploadValidationError("UNSUPPORTED_FILE_FORMAT", "only DOCX files are supported")
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise UploadValidationError("UPLOAD_SIZE_LIMIT", "DOCX upload size limit exceeded", 413)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise UploadValidationError("INVALID_DOCX_PACKAGE", "not an editable DOCX package")
            members = archive.infolist()
            if any(info.flag_bits & 0x1 for info in members):
                raise UploadValidationError("ENCRYPTED_DOCX", "encrypted DOCX is unsupported")
            if len({info.filename for info in members}) != len(members):
                raise UploadValidationError("DUPLICATE_DOCX_MEMBER", "duplicate DOCX member")
            if any(info.file_size > MAX_PART_BYTES for info in members):
                raise UploadValidationError("DOCX_PART_SIZE_LIMIT", "DOCX part size limit exceeded", 413)
            if any(info.file_size > MAX_COMPRESSION_RATIO * max(info.compress_size, 1) for info in members):
                raise UploadValidationError("DOCX_COMPRESSION_RATIO_LIMIT", "DOCX compression ratio limit exceeded", 413)
            if sum(info.file_size for info in members) > MAX_UNCOMPRESSED_BYTES:
                raise UploadValidationError("DOCX_EXPANDED_SIZE_LIMIT", "DOCX expanded size limit exceeded", 413)
    except (zipfile.BadZipFile, zipfile.LargeZipFile):
        raise UploadValidationError("INVALID_DOCX_PACKAGE", "invalid DOCX package") from None
    return safe_name


def has_tracked_revisions(data: bytes) -> bool:
    """Detect Word tracked changes before a delivery task is accepted.

    The delivery engine deliberately refuses documents with existing revision
    marks.  Detecting this at upload time gives the user an actionable error
    instead of a completed task that produces no deliverable.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in archive.namelist():
                if not (name.startswith("word/") and name.endswith(".xml")):
                    continue
                data = archive.read(name)
                if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", data, re.I):
                    continue
                try:
                    root = etree.fromstring(
                        data,
                        parser=etree.XMLParser(resolve_entities=False, no_network=True,
                                               load_dtd=False, huge_tree=False),
                    )
                except (etree.XMLSyntaxError, ValueError):
                    continue
                for element in root.iter():
                    if not isinstance(element.tag, str):
                        continue
                    if (element.tag.startswith("{" + W + "}")
                            and etree.QName(element).localname in REVISION_TAGS):
                        return True
    except (zipfile.BadZipFile, OSError, ValueError):
        return False
    return False


def validate_batch_limits(count: int, total_bytes: int) -> None:
    # File-count limits were removed by product decision; aggregate bytes remain
    # bounded so one request cannot consume unbounded storage/network.
    _ = count
    if total_bytes > MAX_BATCH_BYTES:
        raise UploadValidationError("UPLOAD_REQUEST_SIZE_LIMIT", "upload request size limit exceeded", 413)
