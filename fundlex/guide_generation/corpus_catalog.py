"""Contract catalog, conservative versioning and corpus snapshots."""
from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..guide_generation.models import (
    ContractVersion,
    CorpusSnapshot,
    sha256_bytes,
    stable_id,
)
from ..guide_generation.store import GuideGenerationStore
from .corpus_segmenter import PARSER_VERSION, ContractParseError, SegmentedContract, segment_contract

INDEX_VERSION = "guide-corpus-index-1"
_VERSION_SUFFIX = re.compile(r"^(?P<base>.+?)(?:[_-](?P<date>(?:19|20)\d{6}))?$")
_CONTRACT_SUFFIX = re.compile(r"基金合同.*$")
_NON_CONTRACT = re.compile(r"(?:模板|template|说明|指引|备忘|对比|compare)", re.IGNORECASE)


class CorpusConfigError(RuntimeError):
    """The configured corpus directory cannot serve a run.

    The stable ``code`` distinguishes a missing/misconfigured directory
    (``CORPUS_DIR_MISSING``) from one the process cannot read
    (``CORPUS_DIR_UNREADABLE``).  Both are configuration/deployment faults and
    must never degrade into an empty snapshot that a gate later reports as the
    ambiguous ``CORPUS_EMPTY`` (FL-D821).
    """

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class SyncResult:
    snapshot: CorpusSnapshot
    parsed: int
    reused: int
    skipped: int
    errors: list[dict[str, str]]
    # Eligible contract files found in the directory before ``limit``
    # truncation; callers can tell a truncated scan from an empty corpus.
    eligible_files: int = 0


def _normalise_name(name: str) -> str:
    value = re.sub(r"\s+", "", name or "")
    value = re.sub(r"[（(].*?[）)]", "", value)
    return value


def parse_contract_filename(filename: str) -> tuple[str, str, str]:
    """Return (fund_identity, version_date, display_name) conservatively.

    The archive uses ``<manager><fund>基金合同_YYYYMMDD.docx``.  When a date is
    absent the relation remains unresolved rather than guessing from mtime.
    """
    stem = Path(filename).stem
    date = ""
    match = re.search(r"[_-]((?:19|20)\d{6})$", stem)
    if match:
        date = match.group(1)
        stem = stem[:match.start()]
    display = stem
    identity = _CONTRACT_SUFFIX.sub("", stem).strip("_- ")
    identity = _normalise_name(identity)
    if not identity:
        identity = _normalise_name(display)
    return identity, date, display


def _version_date_label(value: str) -> str:
    if re.fullmatch(r"(?:19|20)\d{6}", value or ""):
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or ""


def scan_corpus_directory(directory: str | Path) -> list[Path]:
    root = Path(directory)
    if not root.is_dir():
        return []
    files = []
    for path in sorted(root.glob("*.docx")):
        if path.name.startswith("~$") or _NON_CONTRACT.search(path.name):
            continue
        files.append(path)
    return files


def _validated_corpus_root(directory: str | Path) -> Path:
    """Fail loudly when the corpus directory is missing or unreadable.

    ``Path.is_dir``/``glob`` semantics differ across platforms and Python
    versions: a sandboxed or permission-denied directory can collapse into a
    silent empty scan, which previously surfaced only as the ambiguous
    ``CORPUS_EMPTY`` two stages later (FL-D820/FL-D821).  ``os.listdir`` gives
    a precise errno so the run fails with an actionable configuration error
    at the first corpus stage instead.
    """
    if not str(directory or "").strip():
        raise CorpusConfigError("CORPUS_DIR_MISSING", "no corpus directory configured")
    root = Path(directory)
    try:
        os.listdir(root)
    except FileNotFoundError:
        raise CorpusConfigError(
            "CORPUS_DIR_MISSING",
            f"corpus directory does not exist: {root}") from None
    except NotADirectoryError:
        raise CorpusConfigError(
            "CORPUS_DIR_MISSING",
            f"corpus path is not a directory: {root}") from None
    except PermissionError:
        raise CorpusConfigError(
            "CORPUS_DIR_UNREADABLE",
            f"corpus directory is not readable by this process: {root}") from None
    except OSError as exc:
        raise CorpusConfigError(
            "CORPUS_DIR_UNREADABLE", f"{root}: {exc}") from None
    return root


def sync_corpus(store: GuideGenerationStore, directory: str | Path, *,
                limit: int | None = None, force: bool = False) -> SyncResult:
    """Parse new/changed contracts and publish one immutable snapshot."""
    store.ensure_schema()
    root = _validated_corpus_root(directory)
    try:
        paths = scan_corpus_directory(root)
    except OSError as exc:
        raise CorpusConfigError(
            "CORPUS_DIR_UNREADABLE", f"cannot scan {root}: {exc}") from None
    eligible = len(paths)
    if limit:
        paths = paths[:limit]
    parsed = reused = skipped = 0
    errors: list[dict[str, str]] = []
    version_ids: list[str] = []
    rows: list[ContractVersion] = []
    for path in paths:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            errors.append({"path": str(path), "code": "CORPUS_READ_FAILED", "detail": type(exc).__name__})
            skipped += 1
            continue
        digest = sha256_bytes(raw)
        identity, date, display = parse_contract_filename(path.name)
        contract_id = stable_id("C", identity, length=20)
        version_id = stable_id("CV", identity, date, digest, length=24)
        version_ids.append(version_id)
        existing = store.get_contract_version(version_id)
        if existing and existing.status == "parsed" and not force:
            rows.append(existing)
            reused += 1
            continue
        try:
            segmented = segment_contract(path, contract_version_id=version_id, source_sha256=digest)
        except ContractParseError as exc:
            errors.append({"path": str(path), "code": exc.code, "detail": str(exc.details)})
            skipped += 1
            version = ContractVersion(
                contract_version_id=version_id, contract_id=contract_id, fund_identity=identity,
                display_name=display, version_date=date, source_sha256=digest,
                source_path=str(path.resolve()), source_size=len(raw), parser_version=PARSER_VERSION,
                status="parse_failed", metadata={"error_code": exc.code},
            )
            store.upsert_contract_version(version)
            rows.append(version)
            continue
        version = ContractVersion(
            contract_version_id=version_id, contract_id=contract_id, fund_identity=identity,
            display_name=display, version_date=date, source_sha256=digest,
            source_path=str(path.resolve()), source_size=len(raw), parser_version=PARSER_VERSION,
            status="parsed", metadata={
                "title": segmented.title, "manager": segmented.manager,
                "custodian": segmented.custodian, "clause_count": len(segmented.clauses),
                "stats": segmented.stats,
            },
        )
        store.upsert_contract_version(version)
        store.replace_clauses(version_id, segmented.clauses)
        parsed += 1
        rows.append(version)

    # Rebuild conservative version relations within each fund identity.
    grouped: dict[str, list[ContractVersion]] = {}
    for version in rows:
        grouped.setdefault(version.fund_identity, []).append(version)
    all_versions: list[ContractVersion] = []
    for identity, versions in grouped.items():
        dated = [item for item in versions if item.version_date]
        undated = [item for item in versions if not item.version_date]
        dated.sort(key=lambda item: item.version_date)
        relation = "resolved"
        if undated and dated:
            relation = "unresolved"
        if len(dated) != len({item.version_date for item in dated}):
            relation = "unresolved"
        previous = ""
        for index, item in enumerate(dated):
            item.previous_version_id = previous
            item.version_relation = relation
            item.latest_known_version = index == len(dated) - 1
            previous = item.contract_version_id
            store.upsert_contract_version(item)
            all_versions.append(item)
        for item in undated:
            item.previous_version_id = ""
            item.version_relation = "unresolved"
            item.latest_known_version = not dated and len(undated) == 1
            store.upsert_contract_version(item)
            all_versions.append(item)

    all_versions.sort(key=lambda item: (item.fund_identity, item.version_date, item.contract_version_id))
    latest = [item.contract_version_id for item in all_versions if item.latest_known_version]
    historical = [item.contract_version_id for item in all_versions if not item.latest_known_version]
    hashes = {item.contract_version_id: item.source_sha256 for item in all_versions}
    snapshot_id = stable_id("SNAP", INDEX_VERSION, PARSER_VERSION,
                            *sorted(f"{key}:{value}" for key, value in hashes.items()), length=24)
    snapshot = CorpusSnapshot(
        snapshot_id=snapshot_id,
        contract_version_ids=[item.contract_version_id for item in all_versions],
        contract_hashes=hashes, latest_version_ids=latest, historical_version_ids=historical,
        parser_version=PARSER_VERSION, index_version=INDEX_VERSION,
        counts={"contracts": len(all_versions), "latest": len(latest), "historical": len(historical),
                "parsed": sum(item.status == "parsed" for item in all_versions),
                "parse_failed": sum(item.status == "parse_failed" for item in all_versions)},
    )
    store.create_snapshot(snapshot)
    return SyncResult(snapshot=snapshot, parsed=parsed, reused=reused, skipped=skipped,
                      errors=errors, eligible_files=eligible)
