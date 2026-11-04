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
# Bounded upload names keep MySQL VARCHAR columns (guide_versions.filename is
# VARCHAR(768)) from rejecting long user input with a 500 (A4-F01).
MAX_FILENAME_BYTES = int(os.environ.get("FUNDLEX_MAX_FILENAME_BYTES", "200"))
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
    if len(safe_name.encode("utf-8")) > MAX_FILENAME_BYTES:
        raise UploadValidationError(
            "UPLOAD_FILENAME_TOO_LONG",
            f"file name exceeds {MAX_FILENAME_BYTES} bytes; rename the file and upload again",
            422)
    suffix = Path(safe_name).suffix.lower()
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


def normalize_contract_upload(name: str, data: bytes) -> tuple[str, bytes, bool]:
    """上传归一：CDF 二进制 \``.doc\``（扩展名或 magic）自动转换后按 DOCX 校验。

    冻结接口（协助 FL-D1057 比对侧复用，与 fundlex.doc_convert 同源）：
    ``(safe_name, normalized_bytes, converted)``。来源/产物 hash 一律以归一
    后的字节为准（source_sha256 记转换产物）；转换失败如实报
    ``LEGACY_DOC_CONVERT_*``（不再是 LEGACY_DOC_UNSUPPORTED 拒绝分支）。
    """
    suffix = Path((name or "").replace("\\", "/")).suffix.lower()
    if suffix == ".doc" or data.startswith(LEGACY_DOC_MAGIC):
        # 展示名沿用原件名（安全名规则与 DOCX 相同）。
        display = Path((name or "").replace("\\", "/")).name
        if len(display.encode("utf-8")) > MAX_FILENAME_BYTES:
            raise UploadValidationError(
                "UPLOAD_FILENAME_TOO_LONG",
                f"file name exceeds {MAX_FILENAME_BYTES} bytes; rename the file and upload again",
                422)
        from .doc_convert import DocConvertError, convert_doc_to_docx
        try:
            converted = convert_doc_to_docx(bytes(data))
        except DocConvertError as exc:
            # 区分 soffice 错误与产品错误：全部如实，不冒称转换。
            raise UploadValidationError(exc.code, exc.user_message) from exc
        # 转换产物按完整 DOCX 包安全链校验（以 .docx 名义过同一闸门）。
        validate_docx_upload(
            Path(display).with_suffix(".docx").name if display else "converted.docx",
            converted)
        return display or "converted.docx", converted, True
    safe_name = validate_docx_upload(name, data)
    return safe_name, bytes(data), False


def has_tracked_revisions(data: bytes) -> bool:
    """Detect Word tracked changes in an uploaded document.

    Detection helper only: tracked inputs are **not** rejected.  Locked
    strategy B (2026-11-02 user ruling): the recall pipeline carries foreign
    marks into delivery and stacks its own new revisions on top; no flattening
    is applied at task input.
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
