"""Bounded, provider-neutral model gateway for verified extraction only.

The gateway never emits edit text or XML. Callers must verify all returned
quotes against the exact bounded context before using a value.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


class ModelError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ModelResult:
    value: dict[str, Any]
    model: str
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    request_id: str | None
    attempts: int


class ModelGateway:
    """OpenAI-compatible transport; no provider-specific business branches."""

    def __init__(self, *, base_url: str, model: str, api_key: str,
                 max_context_chars: int = 2400, max_calls: int = 16,
                 max_completion_tokens: int = 300, timeout_s: float = 35.0,
                 retries: int = 1, client: httpx.Client | None = None):
        if not base_url or not model or not api_key:
            raise ModelError("MODEL_CONFIG_MISSING")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_context_chars = max_context_chars
        self.max_calls = max_calls
        self.max_completion_tokens = max_completion_tokens
        self.timeout_s = timeout_s
        self.retries = retries
        self.calls = 0
        self._client = client or httpx.Client(timeout=timeout_s)

    @classmethod
    def from_env(cls) -> "ModelGateway":
        # The provider label is metadata. The HTTP contract remains generic.
        return cls(base_url=os.environ.get("LLM_BASE_URL", ""),
                   model=os.environ.get("LLM_MODEL", ""),
                   api_key=os.environ.get("LLM_API_KEY", ""),
                   max_context_chars=int(os.environ.get("FUNDLEX_MODEL_CONTEXT_CHARS", "2400")),
                   max_calls=int(os.environ.get("FUNDLEX_MODEL_MAX_CALLS", "16")),
                   max_completion_tokens=int(os.environ.get("FUNDLEX_MODEL_MAX_OUTPUT_TOKENS", "300")),
                   timeout_s=float(os.environ.get("FUNDLEX_MODEL_TIMEOUT_S", "35")))

    def extract_fund_type(self, context: str, *, prompt_version: str = "fund_type_v1") -> ModelResult:
        if not context or len(context) > self.max_context_chars:
            raise ModelError("MODEL_CONTEXT_LIMIT")
        if self.calls >= self.max_calls:
            raise ModelError("MODEL_CALL_BUDGET_EXCEEDED")
        self.calls += 1
        system = (
            "You extract evidence from a Chinese fund contract. Return only JSON with keys "
            "quote and fund_type. quote must be one exact, contiguous substring of the user text "
            "that states the CURRENT fund's category or operating form. "
            "fund_type must be one of etf, interbank_cd, money_market, ordinary, unknown. "
            "ETF feeder/link funds are not ETF. If the current product cannot be established "
            "from this text, use unknown and an empty quote. Do not infer from a contract title alone."
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": f"prompt_version={prompt_version}\n{context}"}],
            "temperature": 0,
            "max_tokens": self.max_completion_tokens,
            "response_format": {"type": "json_object"},
        }
        start = time.monotonic()
        for attempt in range(self.retries + 1):
            try:
                response = self._client.post(
                    self.base_url + "/chat/completions",
                    json=payload,
                    headers={"Authorization": "Bearer " + self.api_key,
                             "Content-Type": "application/json"},
                    timeout=self.timeout_s,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 2))
                    continue
                raise ModelError("MODEL_NETWORK_ERROR") from exc
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 2))
                    continue
                raise ModelError("MODEL_RETRY_EXHAUSTED")
            if response.status_code >= 400:
                raise ModelError("MODEL_HTTP_ERROR")
            try:
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                value = json.loads(content) if isinstance(content, str) else content
                if not isinstance(value, dict) or set(value) != {"quote", "fund_type"}:
                    raise ValueError("shape")
                if not isinstance(value["quote"], str) or value["fund_type"] not in {
                    "etf", "interbank_cd", "money_market", "ordinary", "unknown"
                }:
                    raise ValueError("enum")
                if value["quote"] and value["quote"] not in context:
                    raise ModelError("MODEL_QUOTE_MISMATCH")
                if value["fund_type"] == "unknown" or not value["quote"]:
                    raise ModelError("MODEL_EVIDENCE_UNKNOWN")
                usage = body.get("usage") or {}
                def integer(name: str) -> int | None:
                    raw = usage.get(name)
                    return raw if isinstance(raw, int) and raw >= 0 else None
                return ModelResult(value, str(body.get("model") or self.model),
                                   round((time.monotonic() - start) * 1000),
                                   integer("prompt_tokens"), integer("completion_tokens"),
                                   integer("total_tokens"), response.headers.get("x-request-id"),
                                   attempt + 1)
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ModelError("MODEL_SCHEMA_INVALID") from exc
        raise ModelError("MODEL_RETRY_EXHAUSTED")
