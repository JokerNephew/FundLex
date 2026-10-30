"""The single task orchestration seam shared by Web and integrations."""
from __future__ import annotations

from typing import Any, Callable

from .. import guide_store, model_settings
from ..tasks import TaskStore


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
        guide = self._guide_resolver(owner, guide_version_id)
        # Rule switches are owner configuration.  Resolve them here, not from the
        # request body, and snapshot the result into the task so a later settings
        # change cannot alter an already-created task.
        switches = guide_store.rule_settings(self.store, owner, guide["id"])
        disabled = list(switches.get("disabled_rule_ids") or [])

        # Snapshot settings in the same transaction that inserts the task.
        # This serializes against BYOK reset/rotation and its orphan-key GC.
        model_settings.ensure_schema(self.store)

        def model_snapshot(db):
            return model_settings.snapshot_in_task_transaction(
                db, owner, mysql=self.store.database.dialect == "mysql")

        return self.tasks.create(owner, name, guide, files, idempotency_key,
                                 engine_id="recall_first", guide_version_id=guide["id"],
                                 guide_rules_sha256=guide["rules_sha256"], mode=mode,
                                 disabled_rule_ids=disabled,
                                 model_preferences_factory=model_snapshot)

    def upload_files(self, owner: str, task_id: str, files: list[dict[str, Any]]) -> dict[str, Any]:
        return self.tasks.uploads(owner, task_id, files)

    def seal_task(self, owner: str, task_id: str) -> dict[str, Any]:
        return self.tasks.control(owner, task_id, "seal")

    def get_task(self, owner: str, task_id: str) -> dict[str, Any]:
        return self.tasks.get(owner, task_id)

    def list_documents(self, owner: str, task_id: str, **filters) -> dict[str, Any]:
        return self.tasks.documents(owner, task_id, **filters)
