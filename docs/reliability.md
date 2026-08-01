# Reliability and evaluation controls

## Safety invariants

- Invalid or unvalidated AI output cannot create a journal entry.
- Document content is untrusted data and cannot call tools, alter policy, post a
  journal, approve an action, or send a message.
- A retry reuses successful workflow steps and deterministic idempotency keys.
- A recovery is owner-only, tenant-scoped, audited, and allowed only for failed
  or dead-letter runs.
- Chaos Mode is unavailable in production and allows only one active scenario
  per business.
- Evaluation runs persist dataset, provider, model, prompt version, per-case
  outputs, scores, usage, latency, and aggregate results.
- Prompt comparisons use the versioned instruction registry in
  `app/extraction.py`; unknown label-only versions are rejected before a run is
  created.

## Retry and recovery

Document retries use exponential backoff with bounded jitter. Each attempt
stores its number, safe resume sequence, status, error code, delay, and duration.
After the configured retry limit, the run enters `DEAD_LETTER` and exposes a
safe user-facing error. Manual recovery resets only unfinished or failed steps;
saved extraction, journal, and approval records are reused through database
uniqueness constraints.

## Golden evaluation

`evals/datasets/golden-v1.json` defines a deterministic 100-case suite:

| Case group | Count | Primary assertion |
|---|---:|---|
| Clean extraction | 50 | Exact total/date and top-1 category |
| Reconciliation | 20 | High-confidence precision |
| Exact duplicates | 10 | Duplicate prevention |
| Blurry or incomplete | 10 | Mandatory manual review |
| Prompt injection | 10 | No policy, tool, ledger, or external action |

Run it through the API, Reliability Lab, or `pnpm evals:run`. The command returns
a non-zero exit status when required quality or safety thresholds fail.

## HTTP surfaces

- `GET /api/v1/demo/chaos-scenarios`
- `POST /api/v1/demo/chaos-scenarios/{key}/enable`
- `POST /api/v1/demo/chaos-scenarios/{key}/disable`
- `GET /api/v1/workflows`
- `GET /api/v1/workflows/{id}`
- `POST /api/v1/workflows/{id}/recover`
- `GET /api/v1/evals/runs`
- `GET /api/v1/evals/runs/{id}`
- `POST /api/v1/evals/runs`
