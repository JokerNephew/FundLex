"""Read-only admission guard for the *next* evaluation launcher.

No gateway, service, SQLite writer, model or telemetry client is constructed here.
See ``tools/evaluation/BUDGET_PREFLIGHT.md`` for the frozen protocol and wrapper API.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from types import MappingProxyType
from typing import Callable, Mapping, TypeVar


SCHEMA = "fundlex-evaluation-budget-v1"
MANIFEST_SCHEMA = "fundlex-evaluation-preflight-v1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_COLUMNS = "rowid,id,started,lease_until,status,reserved_cost,charged_cost"
T = TypeVar("T")


class PreflightError(RuntimeError):
    """Safe, stable errors: never interpolate configuration values or SQL errors."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise PreflightError(code)


def _keys(value: object, expected: set[str], field: str) -> dict:
    _require(isinstance(value, dict) and set(value) == expected, f"SCHEMA:{field}")
    return value


def _integer(value: object, field: str, minimum: int = 1) -> int:
    _require(type(value) is int and value >= minimum, f"INVALID:{field}")
    return value


def _money(value: object, field: str, *, zero: bool = False) -> Decimal:
    _require(type(value) in (str, int, float, Decimal), f"INVALID:{field}")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise PreflightError(f"INVALID:{field}") from None
    _require(result.is_finite() and (result >= 0 if zero else result > 0),
             f"INVALID:{field}")
    return result


def _hash(value: object, field: str) -> str:
    _require(isinstance(value, str) and _HASH.fullmatch(value) is not None,
             f"INVALID:{field}")
    return value


def _identifier(value: object, field: str) -> str:
    _require(isinstance(value, str) and _ID.fullmatch(value) is not None,
             f"INVALID:{field}")
    return value


def _path(value: object, field: str) -> Path:
    _require(isinstance(value, (str, Path)) and bool(str(value))
             and "://" not in str(value) and "\x00" not in str(value), f"INVALID:{field}")
    result = Path(value)
    _require(result.is_absolute(), f"ABSOLUTE_PATH_REQUIRED:{field}")
    return result.resolve()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _file_hash(path: Path, field: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise PreflightError(f"UNREADABLE:{field}") from None


def _read_json(path: Path, field: str) -> tuple[dict, str]:
    try:
        raw = path.read_bytes()
        # Duplicate keys must not let the protocol describe two different caps.
        def unique(pairs):
            result = {}
            for key, value in pairs:
                _require(key not in result, f"DUPLICATE_KEY:{field}")
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=unique)
    except (OSError, ValueError):
        raise PreflightError(f"UNREADABLE:{field}") from None
    _require(isinstance(value, dict), f"SCHEMA:{field}")
    return value, hashlib.sha256(raw).hexdigest()


def _ledger(path: Path, prefix_count: int | None = None) -> dict:
    """One consistent read transaction; charged_cost includes reserved attempts.

    Do not use immutable=1: it can ignore a live WAL. Do not instantiate ModelBudget:
    its constructor creates the database/schema and reserve() mutates expired leases.
    """
    try:
        before = path.stat()
        _require(path.is_file(), "LEDGER_MISSING")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            rows = db.execute(f"SELECT {_COLUMNS} FROM requests ORDER BY rowid")
            count, cost, baseline_cost, reserved = 0, Decimal(0), Decimal(0), 0
            digest = hashlib.sha256()
            statuses: dict[str, int] = {}
            for row in rows:
                _require(row[4] in {"completed", "failed", "abandoned", "reserved"},
                         "LEDGER_UNKNOWN_STATUS")
                charge = _money(row[6], "ledger.charged_cost", zero=True)
                _money(row[5], "ledger.reserved_cost", zero=True)
                count += 1
                cost += charge
                reserved += row[4] == "reserved"
                statuses[row[4]] = statuses.get(row[4], 0) + 1
                if prefix_count is None or count <= prefix_count:
                    digest.update(_json_bytes(row) + b"\n")
                    baseline_cost += charge
            after = path.stat()
            _require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
                     "LEDGER_REPLACED")
    except (OSError, sqlite3.Error, ValueError, TypeError):
        raise PreflightError("LEDGER_UNREADABLE_OR_SCHEMA_INVALID") from None
    return {"path": str(path), "device": before.st_dev, "inode": before.st_ino,
            "requests": count, "charged_cost_usd": str(cost),
            "prefix_sha256": digest.hexdigest(), "prefix_cost_usd": str(baseline_cost),
            "reserved_requests": reserved, "statuses": statuses}


def ledger_anchor(path: str | Path) -> dict:
    """Capture existing history for a separately authorized frozen protocol.

    This is evidence, not permission to increase a budget or choose a new ledger.
    """
    usage = _ledger(_path(path, "ledger.path"))
    _require(usage["reserved_requests"] == 0, "LEDGER_HAS_RESERVED_REQUESTS")
    return {key: usage[key] for key in
            ("path", "device", "inode", "requests", "charged_cost_usd", "prefix_sha256")}


def _case_budget(value: object) -> dict:
    data = _keys(value, {"requests", "cost_usd", "max_calls"}, "case_budget")
    calls = _keys(data["max_calls"], {"primary", "review"}, "case_budget.max_calls")
    return {"requests": _integer(data["requests"], "case_budget.requests"),
            "cost_usd": str(_money(data["cost_usd"], "case_budget.cost_usd")),
            "max_calls": {role: _integer(calls[role], "case_budget.max_calls." + role)
                          for role in ("primary", "review")}}


def _config(value: object) -> dict:
    data = _keys(value, {"run_id", "engine_id", "engine_build", "selection_sha256",
                         "labels_sha256", "case_ids", "budget", "case_budget"}, "config")
    budget = _keys(data["budget"], {"ledger_path", "max_requests", "max_cost_usd",
                                    "concurrency", "input_usd_per_million",
                                    "output_usd_per_million"}, "budget")
    case_ids = data["case_ids"]
    _require(isinstance(case_ids, list) and bool(case_ids), "INVALID:case_ids")
    cases = [_identifier(case, "case_id") for case in case_ids]
    _require(len(set(cases)) == len(cases), "DUPLICATE_CASE_IDS")
    return {"run_id": _identifier(data["run_id"], "run_id"),
            "engine_id": _identifier(data["engine_id"], "engine_id"),
            "engine_build": _hash(data["engine_build"], "engine_build"),
            "selection_sha256": _hash(data["selection_sha256"], "selection_sha256"),
            "labels_sha256": _hash(data["labels_sha256"], "labels_sha256"),
            "case_ids": cases, "case_budget": _case_budget(data["case_budget"]),
            "budget": {"ledger_path": str(_path(budget["ledger_path"], "ledger_path")),
                       "max_requests": _integer(budget["max_requests"], "max_requests"),
                       "concurrency": _integer(budget["concurrency"], "concurrency"),
                       **{key: str(_money(budget[key], key)) for key in
                          ("max_cost_usd", "input_usd_per_million", "output_usd_per_million")}}}


@dataclass(frozen=True)
class StartupPlan:
    """Actual launcher arguments, supplied independently of the frozen protocol.

    requests_per_case/cost_per_case_usd are conservative admission allowances for
    ALL attempts (including retries/repair); max_calls comes from resolved roles.
    """
    run_id: str
    selection: Path
    labels: Path
    case_ids: tuple[str, ...]
    requests_per_case: int
    cost_per_case_usd: str
    engine_id: str = "recall_first"


def _startup(plan: StartupPlan) -> tuple[dict, dict[str, str]]:
    # Read-only resolvers only. Import neither gateways nor the application.
    from fundlex.config import local_data_dir
    from fundlex.models.config import load_role_config
    from fundlex.store import engine_build

    env = dict(os.environ)
    _require(env.get("FUNDLEX_MODEL_MODE", "live") in {"live", "record"},
             "UNSUPPORTED_MODEL_MODE")
    selection, selection_hash = _read_json(Path(plan.selection), "selection")
    labels_hash = _file_hash(Path(plan.labels), "labels")
    cases = selection.get("cases")
    _require(isinstance(cases, list), "SCHEMA:selection.cases")
    _require(all(isinstance(case, dict) and isinstance(case.get("case_id"), str)
                 for case in cases), "SCHEMA:selection.cases")
    available = [case["case_id"] for case in cases]
    _require(len(set(available)) == len(available), "DUPLICATE_SELECTION_CASE_IDS")
    _require(set(plan.case_ids) <= set(available), "CASE_NOT_IN_SELECTION")
    try:
        roles, _ = load_role_config()
        budget = {"ledger_path": env.get("FUNDLEX_MODEL_LEDGER",
                                         str(local_data_dir() / "model_budget.sqlite")),
                  "max_requests": int(env.get("FUNDLEX_MODEL_MAX_REQUESTS", "16")),
                  "max_cost_usd": env.get("FUNDLEX_MODEL_MAX_COST_USD", "1"),
                  "concurrency": int(env.get("FUNDLEX_MODEL_CONCURRENCY", "1")),
                  "input_usd_per_million": env.get("FUNDLEX_MODEL_INPUT_USD_PER_M", "1"),
                  "output_usd_per_million": env.get("FUNDLEX_MODEL_OUTPUT_USD_PER_M", "5")}
        case_budget = {"requests": plan.requests_per_case, "cost_usd": plan.cost_per_case_usd,
                       "max_calls": {role: roles[role].max_calls for role in ("primary", "review")}}
    except (ValueError, KeyError, TypeError, OSError):
        raise PreflightError("STARTUP_CONFIGURATION_INVALID") from None
    _require(env == dict(os.environ), "STARTUP_ENVIRONMENT_CHANGED")
    return _config({"run_id": plan.run_id, "engine_id": plan.engine_id,
                    "engine_build": engine_build(), "selection_sha256": selection_hash,
                    "labels_sha256": labels_hash, "case_ids": list(plan.case_ids),
                    "budget": budget, "case_budget": case_budget}), env


def _check(protocol: dict, actual: dict) -> dict:
    _keys(protocol, {"schema", "authorization_id", "config", "ledger_anchor"}, "protocol")
    _require(protocol["schema"] == SCHEMA, "SCHEMA:protocol.version")
    _identifier(protocol["authorization_id"], "authorization_id")
    frozen = _config(protocol["config"])
    # Decimal numeric equality permits 2, 2.0 and '2.00', never a higher cap.
    for field in frozen:
        if field in {"budget", "case_budget"}:
            for key in frozen[field]:
                left, right = frozen[field][key], actual[field][key]
                if key.endswith("usd") or key.endswith("per_million"):
                    left, right = Decimal(left), Decimal(right)
                _require(left == right, f"CONFIG_MISMATCH:{field}.{key}")
        else:
            _require(frozen[field] == actual[field], f"CONFIG_MISMATCH:{field}")
    anchor = _keys(protocol["ledger_anchor"], {"path", "device", "inode", "requests",
                                               "charged_cost_usd", "prefix_sha256"}, "ledger_anchor")
    path = _path(anchor["path"], "ledger_anchor.path")
    _require(str(path) == frozen["budget"]["ledger_path"], "LEDGER_PATH_MISMATCH")
    baseline_count = _integer(anchor["requests"], "ledger_anchor.requests", minimum=0)
    baseline_cost = _money(anchor["charged_cost_usd"], "ledger_anchor.cost", zero=True)
    for field in ("device", "inode"):
        _integer(anchor[field], "ledger_anchor." + field, minimum=0)
    _hash(anchor["prefix_sha256"], "ledger_anchor.prefix_sha256")
    usage = _ledger(path, baseline_count)
    _require(all(usage[key] == anchor[key] for key in ("device", "inode")), "LEDGER_IDENTITY_MISMATCH")
    _require(usage["requests"] >= baseline_count
             and usage["prefix_sha256"] == anchor["prefix_sha256"]
             and Decimal(usage["prefix_cost_usd"]) == baseline_cost, "LEDGER_HISTORY_MISMATCH")
    _require(usage["reserved_requests"] == 0, "LEDGER_HAS_RESERVED_REQUESTS")
    remaining_requests = actual["budget"]["max_requests"] - usage["requests"]
    remaining_cost = Decimal(actual["budget"]["max_cost_usd"]) - Decimal(usage["charged_cost_usd"])
    _require(remaining_requests >= 0 and remaining_cost >= 0, "LEDGER_ALREADY_OVER_CAP")
    required_requests = len(actual["case_ids"]) * actual["case_budget"]["requests"]
    required_cost = len(actual["case_ids"]) * Decimal(actual["case_budget"]["cost_usd"])
    _require(required_requests <= remaining_requests and required_cost <= remaining_cost,
             "INSUFFICIENT_RUN_BALANCE")
    return {"ledger": usage, "remaining_requests": remaining_requests,
            "remaining_cost_usd": str(remaining_cost), "required_requests": required_requests,
            "required_cost_usd": str(required_cost)}


def _admit(protocol_path: Path, protocol_sha256: str, plan: StartupPlan,
           manifest_path: Path) -> tuple[dict, dict[str, str]]:
    expected = _hash(protocol_sha256, "protocol_sha256")
    protocol, digest = _read_json(Path(protocol_path), "protocol")
    _require(digest == expected, "PROTOCOL_HASH_MISMATCH")
    actual, env = _startup(plan)
    evidence = _check(protocol, actual)
    # Whitelist only: never serialize env, role safe_dict(), URLs, headers or metadata.
    manifest = {"schema": MANIFEST_SCHEMA, "status": "PREFLIGHT_PASSED",
                "protocol_sha256": digest, "authorization_id": protocol["authorization_id"],
                "config": actual, "evidence": evidence,
                "scope": "admission_snapshot_not_a_reservation_or_delivery_acceptance"}
    encoded = _json_bytes(manifest) + b"\n"
    try:
        # O_EXCL also rejects symlinks (including dangling links). No mkdir/overwrite.
        descriptor = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
    except FileExistsError:
        raise PreflightError("MANIFEST_ALREADY_EXISTS") from None
    except OSError:
        raise PreflightError("MANIFEST_WRITE_FAILED") from None
    return manifest, env


def preflight(protocol_path: Path, *, protocol_sha256: str, plan: StartupPlan,
              manifest_path: Path) -> dict:
    """Validate the actual process configuration and publish one new manifest."""
    return _admit(protocol_path, protocol_sha256, plan, manifest_path)[0]


def guarded_start(protocol_path: Path, *, protocol_sha256: str, plan: StartupPlan,
                  manifest_path: Path, start: Callable[[Mapping[str, str]], T]) -> T:
    """Next-run wrapper: callback is unreachable on failed admission.

    The callback must launch local services/runner using the supplied environment
    unchanged. It must use plan's exact run/case arguments, without cap overrides.
    """
    _, env = _admit(protocol_path, protocol_sha256, plan, manifest_path)
    return start(MappingProxyType(env))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--case", action="append", required=True)
    parser.add_argument("--requests-per-case", type=int, required=True)
    parser.add_argument("--cost-per-case-usd", required=True)
    parser.add_argument("--engine-id", default="recall_first")
    args = parser.parse_args(argv)
    try:
        preflight(args.protocol, protocol_sha256=args.protocol_sha256,
                  plan=StartupPlan(args.run_id, args.selection, args.labels, tuple(args.case),
                                   args.requests_per_case, args.cost_per_case_usd, args.engine_id),
                  manifest_path=args.manifest)
    except PreflightError as exc:
        print(f"PREFLIGHT_REJECTED:{exc}")
        return 2
    print("PREFLIGHT_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
