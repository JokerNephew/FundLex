"""Immutable model cassettes and integrity-checked run inputs for offline replay."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

import jsonschema


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                      prefix=".frozen-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class FrozenError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ModelCassette:
    _locks_guard = threading.Lock()
    _locks: dict[str, Any] = {}

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _path(self, request: dict[str, Any]) -> Path:
        task = str(request["task_type"])
        if not re.fullmatch(r"[a-zA-Z0-9_]+", task):
            raise FrozenError("MODEL_CASSETTE_TASK_INVALID")
        identity = {key: request[key] for key in
                    ("task_type", "prompt_version", "configured_model", "context_sha256")}
        return self.directory / task / (digest(request) + ".json")

    def request_lock(self, request: dict) -> Any:
        key = str(self.directory.resolve()) + ":" + digest(request)
        with self._locks_guard:
            return self._locks.setdefault(key, threading.RLock())

    def load(self, request: dict[str, Any], schema: dict) -> tuple[dict, dict]:
        path = self._path(request)
        if not path.exists():
            # Read legacy recordings without rewriting their immutable contents.
            identity = {key: request[key] for key in
                        ("task_type", "prompt_version", "configured_model", "context_sha256")}
            legacy = path.parent / (digest(identity) + ".json")
            if legacy.exists():
                path = legacy
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            body = envelope["body"]
            if envelope["sha256"] != digest(body) or body["request"] != request:
                raise FrozenError("MODEL_CASSETTE_MISMATCH")
            if not body["event"].get("error_code"):
                jsonschema.validate(body["response"], schema)
            return body["response"], body["event"]
        except FileNotFoundError as exc:
            raise FrozenError("MODEL_REPLAY_MISS") from exc
        except (KeyError, TypeError, ValueError, jsonschema.ValidationError) as exc:
            if isinstance(exc, FrozenError):
                raise
            raise FrozenError("MODEL_CASSETTE_INVALID") from exc

    def save(self, request: dict, response: Any, event: dict) -> None:
        path = self._path(request)
        # Capture ONLY the semantic request. Never headers, API keys, endpoint URLs,
        # environment variables or transport object representations.
        safe_event = {key: event.get(key) for key in (
            "task_type", "prompt_version", "context_sha256", "configured_model",
            "actual_model", "http_status", "finish_reason", "error_code")}
        body = {"schema_version": "fundlex-model-cassette-v1", "request": request,
                "response": response, "event": safe_event}
        envelope = {"body": body, "sha256": digest(body)}
        path.parent.mkdir(parents=True, exist_ok=True)
        # Publish a fully written inode atomically. Concurrent readers never observe
        # a half-written cassette, and an existing recording cannot be overwritten.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                              prefix=".cassette-", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(envelope, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, path)
        except FileExistsError:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != envelope:
                raise FrozenError("MODEL_CASSETTE_CONFLICT") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class FrozenRun:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def boundary(self, stage: str, inputs: dict) -> None:
        if not re.fullmatch(r"[a-z_]+", stage):
            raise FrozenError("FROZEN_STAGE_INVALID")
        path = self.directory / "stages" / (stage + ".json")
        # Stable boundary inputs describe what this stage consumed. Repaired stages
        # get separate revisions so debugging can replay the first failure too.
        revision = 0
        while path.exists():
            revision += 1
            path = self.directory / "stages" / f"{stage}-{revision}.json"
        atomic_json(path, {"schema_version": "fundlex-stage-v1", "stage": stage,
                           "inputs": inputs, "inputs_sha256": digest(inputs)})

    def start(self, source: Path, guide: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        original = self.directory / "original.docx"
        if original.exists() and original.read_bytes() != source.read_bytes():
            raise FrozenError("FROZEN_SOURCE_MISMATCH")
        if not original.exists():
            shutil.copyfile(source, original)
        path = self.directory / "guide.json"
        if path.exists() and json.loads(path.read_text(encoding="utf-8")) != guide:
            raise FrozenError("FROZEN_GUIDE_MISMATCH")
        atomic_json(path, guide)

    def snapshot(self, report: dict, output: Path, *, edits: Any = None) -> None:
        fields = {"facts": "facts", "scope": "scope_mapping", "targets": "targets",
                  "obligations": "obligations", "plan": "plan", "claim_replay": "artifact_claim_replay",
                  "audit": "audit", "sweep": "sweep", "report": None}
        for name, key in fields.items():
            atomic_json(self.directory / (name + ".json"), report if key is None else report.get(key, {}))
        atomic_json(self.directory / "applicability.json", {
            item["obligation_id"]: item.get("applicability")
            for item in (report.get("obligations") or {}).get("records", [])})
        if edits is not None:
            atomic_json(self.directory / "edits.json", edits)
        for name in (report.get("artifacts") or {}).values():
            source = output / name
            if source.is_file() and source.parent == output:
                shutil.copyfile(source, self.directory / source.name)
        manifest = {path.relative_to(self.directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted(self.directory.rglob("*"))
                    if path.is_file() and path.name != "manifest.json"}
        atomic_json(self.directory / "manifest.json", manifest)

    def verify(self) -> None:
        manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not {"original.docx", "guide.json", "report.json"} <= manifest.keys():
            raise FrozenError("FROZEN_MANIFEST_INVALID")
        for name, sha in manifest.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise FrozenError("FROZEN_PATH_INVALID")
            path = self.directory / name
            if (not path.is_file() or path.is_symlink() or
                    not path.resolve().is_relative_to(self.directory.resolve()) or
                    hashlib.sha256(path.read_bytes()).hexdigest() != sha):
                raise FrozenError("FROZEN_INTEGRITY_MISMATCH:" + name)
        actual = {path.relative_to(self.directory).as_posix() for path in self.directory.rglob("*")
                  if path.is_file() and path.name != "manifest.json"}
        if actual != set(manifest):
            raise FrozenError("FROZEN_UNREGISTERED_INPUT")
