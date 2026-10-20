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

    def count(self, action: RecoveryAction, *,
              context: RecoveryContext | None = None) -> int:
        """Attempts of one action, optionally scoped to one obligation identity.

        Budgets are per obligation/target: one target's failed deterministic retry must
        not consume the retry another target never used.
        """
        items = [item for item in self.attempts if item.action is action]
        if context is not None:
            items = [item for item in items
                     if item.rule_id == context.rule_id
                     and item.obligation_id == context.obligation_id
                     and item.target_id == context.target_id
                     and item.site_id == context.site_id]
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
            if context is not None and (
                    item.rule_id != context.rule_id
                    or item.obligation_id != context.obligation_id
                    or item.target_id != context.target_id
                    or item.site_id != context.site_id):
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
