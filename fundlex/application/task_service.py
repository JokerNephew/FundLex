"""The single task orchestration seam shared by Web and integrations."""
from __future__ import annotations

import os
from typing import Any, Callable

from .. import guide_store
from ..direct_pipeline import ENGINE_ID as DIRECT_ENGINE_ID, ENGINE_VERSION as DIRECT_ENGINE_VERSION
from ..tasks import TaskStore


def _model_snapshot(owner_prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Non-secret model configuration snapshot frozen at task creation.

    解析序（FL-D1083 同波）：用户在工作台「设置-模型」的选择 > 管理员系统
    默认 > 部署 env。三键无凭据。"""
    prefs = owner_prefs or {}
    primary = prefs.get("primary") if isinstance(prefs.get("primary"), dict) else {}
    return {"provider": str(primary.get("provider") or os.environ.get("LLM_PROVIDER", "")),
            "base_url": str(primary.get("base_url") or os.environ.get("LLM_BASE_URL", "")),
            "model": str(primary.get("model") or os.environ.get("LLM_MODEL", ""))}


def _owner_model_prefs(store, owner: str) -> dict[str, Any]:
    from .. import model_settings
    try:
        user = model_settings.snapshot(store, owner)
        if user:
            return user
    except model_settings.ModelSettingsError:
        raise ValueError("MODEL_SETTINGS_INVALID") from None
    try:
        return model_settings.snapshot_system_default(store) or {}
    except model_settings.ModelSettingsError:
        return {}


class TaskApplicationService:
    def __init__(self, store, tasks: TaskStore, guide_resolver: Callable[[str, str | None], dict[str, Any]] | None = None):
        self.store = store
        self.tasks = tasks
        self._guide_resolver = guide_resolver or self._resolve_guide

    def _resolve_guide(self, owner: str, guide_version_id: str | None) -> dict[str, Any]:
        requested = (guide_version_id or "").strip()
        try:
            version = (guide_store.get_version(self.store, owner, requested) if requested
                       else guide_store.current_guide(self.store, owner))
        except KeyError as exc:
            raise ValueError("GUIDE_NOT_FOUND") from exc
        if version["status"] not in guide_store.ENABLEABLE_STATUSES:
            raise ValueError("GUIDE_NOT_READY")
        return version

    def create_task(self, owner: str, name: str, files: list[dict[str, Any]], *,
                    guide_version_id: str | None = None, idempotency_key: str | None = None,
                    mode: str = "delivery") -> dict[str, Any]:
        guide = self._resolve_guide(owner, guide_version_id)
        schema = str(guide.get("schema_version") or "")
        if schema != guide_store.CARD_SCHEMA_VERSION:
            # Historical guide-rules-v1 versions stay read-only; a new task must
            # never fall back into the retired engine's interpretation of them.
            raise ValueError("GUIDE_SCHEMA_UNSUPPORTED")
        if mode != "delivery":
            # Direct-through delivery is the only wired mode; evaluation/diagnosis
            # keep their offline runners until the integration line migrates them.
            raise ValueError("TASK_MODE_UNSUPPORTED")
        return self.tasks.create(owner, name, guide, files, idempotency_key,
                                 engine_id=DIRECT_ENGINE_ID, guide_version_id=guide["id"],
                                 guide_rules_sha256=guide["rules_sha256"],
                                 guide_schema_version=schema,
                                 engine_version=DIRECT_ENGINE_VERSION,
                                 snapshot={"model": _model_snapshot(_owner_model_prefs(self.store, owner)),
                                          "rule_switches": {}},
                                 mode=mode)

    def upload_files(self, owner: str, task_id: str, files: list[dict[str, Any]]) -> dict[str, Any]:
        return self.tasks.uploads(owner, task_id, files)

    def seal_task(self, owner: str, task_id: str) -> dict[str, Any]:
        return self.tasks.control(owner, task_id, "seal")

    def get_task(self, owner: str, task_id: str) -> dict[str, Any]:
        return self.tasks.get(owner, task_id)

    def list_documents(self, owner: str, task_id: str, **filters) -> dict[str, Any]:
        return self.tasks.documents(owner, task_id, **filters)
