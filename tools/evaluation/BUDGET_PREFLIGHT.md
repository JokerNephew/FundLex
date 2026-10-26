# Evaluation budget preflight

`budget_preflight.py` is a standalone, offline admission guard for a new
evaluation run. It is deliberately separate from `p6_run.py`; existing runners
keep their public arguments and behavior until a caller explicitly wraps them.

## Frozen protocol

The protocol is a JSON file with schema `fundlex-evaluation-budget-v1`:

```json
{
  "schema": "fundlex-evaluation-budget-v1",
  "authorization_id": "approved-budget-2026-10-26",
  "config": {
    "run_id": "eval-01",
    "engine_id": "recall_first",
    "engine_build": "<sha256>",
    "selection_sha256": "<sha256>",
    "labels_sha256": "<sha256>",
    "case_ids": ["D01"],
    "model_mode": "live",
    "roles": {
      "primary": {
        "provider": "provider-name", "model": "model-name",
        "endpoint_sha256": "<sha256>", "max_context_chars": 12000,
        "max_tokens": 1500, "retries": 1, "max_calls": 16,
        "request_options_sha256": "<sha256>",
        "extra_headers_sha256": "<sha256>", "credential_configured": true,
        "user_agent": "fundlex/0.3.0"
      },
      "review": {
        "provider": "provider-name", "model": "model-name",
        "endpoint_sha256": "<sha256>", "max_context_chars": 12000,
        "max_tokens": 1500, "retries": 1, "max_calls": 16,
        "request_options_sha256": "<sha256>",
        "extra_headers_sha256": "<sha256>", "credential_configured": true,
        "user_agent": "fundlex/0.3.0"
      }
    },
    "budget": {
      "ledger_path": "/absolute/path/to/ledger.sqlite",
      "max_requests": 2000,
      "max_cost_usd": "2",
      "concurrency": 1,
      "input_usd_per_million": "1",
      "output_usd_per_million": "5"
    },
    "case_budget": {
      "requests": 192,
      "cost_usd": "0.2",
      "max_calls": {"primary": 16, "review": 16}
    }
  },
  "ledger_anchor": {
    "path": "/absolute/path/to/ledger.sqlite",
    "device": 0,
    "inode": 0,
    "requests": 0,
    "charged_cost_usd": "0",
    "prefix_sha256": "<sha256>"
  }
}
```

The protocol file is passed with its SHA-256. The guard compares the resolved
selection and labels bytes, engine build, run and case identity, all budget
limits, role call limits, and the actual ledger path. It opens SQLite with
`mode=ro` and `query_only`; it does not create a missing ledger, expire leases,
reserve calls, or modify rows. The anchor proves that the existing history is
the history authorized by the protocol, so selecting a new empty ledger cannot
evade a prior balance.

The case request and cost allowances must include retries and repair attempts.
The guard requires the complete allowance for every selected case to fit in the
remaining request and charged-cost balance. Any mismatch or missing evidence
rejects the run before the caller starts a service or model work.

## CLI

```bash
.venv/bin/python -m tools.evaluation.budget_preflight \
  --protocol /absolute/run/protocol.json \
  --protocol-sha256 <protocol-sha256> \
  --manifest /absolute/run/preflight.json \
  --run-id eval-01 \
  --selection /absolute/input/selection.json \
  --labels /absolute/input/labels.json \
  --case D01 --requests-per-case 192 --cost-per-case-usd 0.2
```

The manifest path must be new. It is opened with `O_EXCL`, mode `0600`, and is
never overwritten. It contains only the safe normalized configuration,
hashes, counts and budget evidence. It contains no API key, header, or endpoint
URL. A successful CLI invocation only admits a run; it does not reserve budget
or launch a runner.

## Launcher callback

For a next-run integration, import `StartupPlan` and call:

```python
guarded_start(
    protocol_path,
    protocol_sha256=protocol_sha256,
    plan=StartupPlan(run_id, selection, labels, tuple(case_ids),
                     requests_per_case, cost_per_case_usd),
    manifest_path=preflight_manifest,
    start=lambda env: launch_existing_runner(env),
)
```

`start` is unreachable on rejection and receives a read-only copy of the
unchanged process environment. The integration must pass the same run and case
arguments to the existing runner and must not add cap overrides. The current
`p6_run.py` is intentionally not modified by this module.
