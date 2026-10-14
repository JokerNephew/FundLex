"""Process-shared request, concurrency and estimated-cost limits for local runs.

The first argument accepts either a SQLite file path (local profile) or a
``mysql://`` URL (shared production ledger).
"""
from __future__ import annotations
import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .db import Database

class BudgetError(RuntimeError):
    pass

class ModelBudget:
    """Every HTTP attempt reserves worst-case cost; missing usage keeps that charge."""
    def __init__(self, path: str | Path, *, max_requests: int = 16,
                 max_cost_usd: float = 1.0, concurrency: int = 1,
                 input_usd_per_million: float = 1.0, output_usd_per_million: float = 5.0,
                 circuit_failures: int = 3, circuit_cooldown_s: float = 120):
        if min(max_requests, concurrency) < 1 or min(max_cost_usd, input_usd_per_million, output_usd_per_million) <= 0:
            raise ValueError('model budget and rates must be positive')
        self.database = Database(path, timeout=20)
        if self.database.path is not None:
            self.path = self.database.path
            self.path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.path = None
        self.max_requests, self.max_cost_usd, self.concurrency = max_requests, max_cost_usd, concurrency
        self.input_rate, self.output_rate = input_usd_per_million, output_usd_per_million
        self.circuit_failures,self.circuit_cooldown_s=circuit_failures,circuit_cooldown_s
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, started REAL NOT NULL, lease_until REAL NOT NULL,
                status TEXT NOT NULL, reserved_cost REAL NOT NULL, charged_cost REAL NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}')""")
    @contextmanager
    def _connect(self):
        with self.database.connect() as db:
            yield db
    def estimate(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens*self.input_rate + output_tokens*self.output_rate)/1_000_000
    def reserve(self, *, input_token_bound: int, output_token_bound: int, lease_seconds: float) -> str:
        cost, now = self.estimate(input_token_bound, output_token_bound), time.time()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE requests SET status='abandoned' WHERE status='reserved' AND lease_until<=?", (now,))
            recent=db.execute("SELECT started,metadata FROM requests WHERE status IN ('completed','failed') ORDER BY started DESC LIMIT ?",(self.circuit_failures,)).fetchall()
            service_errors={'MODEL_NETWORK_ERROR','MODEL_RETRY_EXHAUSTED','MODEL_HTTP_ERROR'}
            if len(recent)==self.circuit_failures and now-recent[0]['started']<self.circuit_cooldown_s and all(json.loads(r['metadata']).get('error_code') in service_errors for r in recent):
                raise BudgetError('MODEL_CIRCUIT_OPEN')
            row = db.execute('SELECT COUNT(*) n,COALESCE(SUM(charged_cost),0) cost FROM requests').fetchone()
            if row['n'] >= self.max_requests: raise BudgetError('MODEL_GLOBAL_CALL_BUDGET_EXCEEDED')
            if row['cost']+cost > self.max_cost_usd: raise BudgetError('MODEL_COST_BUDGET_EXCEEDED')
            if db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0] >= self.concurrency:
                raise BudgetError('MODEL_CONCURRENCY_LIMIT')
            reservation = uuid.uuid4().hex
            db.execute("INSERT INTO requests(id,started,lease_until,status,reserved_cost,charged_cost) VALUES(?,?,?,'reserved',?,?)",
                       (reservation,now,now+lease_seconds,cost,cost))
        return reservation
    def finish(self, reservation: str, metadata: dict, *, prompt_tokens: int | None,
               completion_tokens: int | None, success: bool) -> float:
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM requests WHERE id=?',(reservation,)).fetchone()
            if not row or row['status'] != 'reserved': raise BudgetError('MODEL_RESERVATION_EXPIRED')
            cost = row['reserved_cost']
            if prompt_tokens is not None and completion_tokens is not None:
                cost = self.estimate(prompt_tokens,completion_tokens)
            db.execute('UPDATE requests SET status=?,charged_cost=?,metadata=? WHERE id=?',
                       ('completed' if success else 'failed',cost,json.dumps(metadata,ensure_ascii=False),reservation))
        return cost
    def snapshot(self) -> dict:
        with self._connect() as db:
            row = db.execute('SELECT COUNT(*) calls,COALESCE(SUM(charged_cost),0) cost FROM requests').fetchone()
            statuses = {r['status']:r['n'] for r in db.execute('SELECT status,COUNT(*) n FROM requests GROUP BY status')}
        return {'http_attempts':row['calls'],'estimated_cost_usd':row['cost'],
                'max_http_attempts':self.max_requests,'max_cost_usd':self.max_cost_usd,
                'concurrency':self.concurrency,'statuses':statuses,
                'rates_usd_per_million':{'input':self.input_rate,'output':self.output_rate},
                'cost_is_provider_invoice':False}
