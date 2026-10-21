"""Recovery history (plan §18.3).

The history answers the question a user or a corpus reviewer actually asks:
*why* did this obligation end unresolved?  It records every attempt, its outcome
and the next failure, and is serialisable into the report.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from .types import RecoveryAction, RecoveryAttempt, RecoveryContext


@dataclass
class RecoveryHistory:
    attempts: list[RecoveryAttempt] = field(default_factory=list)

    def append(self, attempt: RecoveryAttempt) -> RecoveryAttempt:
        self.attempts.append(attempt)
        return attempt

    def extend(self, attempts: Iterable[RecoveryAttempt]) -> None:
        self.attempts.extend(attempts)

    @staticmethod
    def _same_subject(item: RecoveryAttempt, context: RecoveryContext) -> bool:
        """Match recovery budgets to a stable business identity.

        Target ids are discovery artifacts and may be regenerated when an inventory
        window is refreshed.  They therefore cannot partition retry budgets.  A
        bound operation/site (or obligation/site when an operation is unavailable) is
        stable across discovery rounds and is the identity used for retry accounting.
        Target id remains a fallback for legacy, unbound diagnostics only.
        """
        if item.rule_id != context.rule_id or item.site_id != context.site_id:
            return False
        source_span = str(context.metadata.get("source_span") or "")
        if item.source_span and source_span and item.source_span != source_span:
            return False
        operation = str(context.operation_id or "")
        obligation = str(context.obligation_id or "")
        item_operation = str(item.operation_id or "")
        item_obligation = str(item.obligation_id or "")
        if operation or item_operation:
            return operation == item_operation
        if obligation or item_obligation:
            return obligation == item_obligation
        # Legacy contexts with no stable operation/obligation are still isolated by
        # target id, preserving the old behavior where no better identity exists.
        return str(item.target_id or "") == str(context.target_id or "")

    def count(self, action: RecoveryAction, *,
              context: RecoveryContext | None = None) -> int:
        """Attempts of one action, optionally scoped to one obligation identity.

        Budgets are per operation/site. Discovery may assign a new target id to the
        same site after an inventory refresh; that must not reset the budget.
        """
        items = [item for item in self.attempts if item.action is action]
        if context is not None:
            items = [item for item in items if self._same_subject(item, context)]
        return len(items)

    def attempted(self, action: RecoveryAction, *, stage: str | None = None,
                  error_code: str | None = None) -> bool:
        for item in self.attempts:
            if item.action is not action:
                continue
            if stage is not None and item.stage != stage:
                continue
            if error_code is not None and item.error_code != error_code:
                continue
            return True
        return False

    def identical_attempt(self, action: RecoveryAction, *, stage: str,
                          error_code: str, reason: str,
                          context: RecoveryContext | None = None) -> bool:
        """Plan §20: the exact same method must not repeat unchanged."""
        for item in self.attempts:
            if item.action is not action or item.stage != stage:
                continue
            if item.error_code != error_code or item.reason != reason:
                continue
            if context is not None and not self._same_subject(item, context):
                continue
            return True
        return False

    def last_failure(self) -> RecoveryAttempt | None:
        for item in reversed(self.attempts):
            if item.outcome in {"failed", "pending"}:
                return item
        return None

    @property
    def terminal(self) -> bool:
        return bool(self.attempts) and \
            self.attempts[-1].action is RecoveryAction.MARK_UNRESOLVED

    def as_list(self) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self.attempts]

    def to_json(self) -> str:
        return json.dumps(self.as_list(), ensure_ascii=False, separators=(",", ":"))

    def summary(self, context: RecoveryContext | None = None) -> dict[str, Any]:
        return {
            "subject": context.as_dict() if context else {},
            "attempts": len(self.attempts),
            "actions": [item.action.value for item in self.attempts],
            "final": self.attempts[-1].outcome if self.attempts else "not_started",
            "history": self.as_list(),
        }
