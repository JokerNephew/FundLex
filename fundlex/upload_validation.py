"""Shared, bounded DOCX upload validation for every task ingress."""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

MAX_UPLOAD_BYTES = int(os.environ.get("FUNDLEX_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_UNCOMPRESSED_BYTES = int(os.environ.get("FUNDLEX_MAX_UNCOMPRESSED_BYTES", str(200 * 1024 * 1024)))
MAX_BATCH_DOCUMENTS = int(os.environ.get("FUNDLEX_MAX_BATCH_DOCUMENTS", "20"))
MAX_BATCH_BYTES = int(os.environ.get("FUNDLEX_MAX_BATCH_BYTES", str(50 * 1024 * 1024)))
MAX_PART_BYTES = int(os.environ.get("FUNDLEX_MAX_PART_BYTES", str(32 * 1024 * 1024)))
MAX_COMPRESSION_RATIO = int(os.environ.get("FUNDLEX_MAX_COMPRESSION_RATIO", "100"))


class UploadValidationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 415):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def validate_docx_upload(name: str, data: bytes) -> str:
    """Validate one DOCX using the same limits as the Web task API."""
    safe_name = Path((name or "").replace("\\", "/")).name
    if not safe_name or not safe_name.lower().endswith(".docx"):
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


def validate_batch_limits(count: int, total_bytes: int) -> None:
    if count > MAX_BATCH_DOCUMENTS:
        raise UploadValidationError("UPLOAD_DOCUMENT_COUNT_LIMIT", "upload request document count limit exceeded", 413)
    if total_bytes > MAX_BATCH_BYTES:
        raise UploadValidationError("UPLOAD_REQUEST_SIZE_LIMIT", "upload request size limit exceeded", 413)
