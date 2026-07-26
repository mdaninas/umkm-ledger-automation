# UMKM Finance Autopilot

**UMKM** stands for *Usaha Mikro, Kecil, dan Menengah*, the Indonesian term for
micro, small, and medium enterprises (MSMEs). These businesses are central to
Indonesia's economy, yet many still manage receipts, invoices, and financial
records through disconnected chats, spreadsheets, and paper archives.

UMKM Finance Autopilot turns those inputs into controlled and traceable finance
workflows. A document enters a private inbox, is extracted in the background,
passes deterministic validation and duplicate checks, becomes a balanced draft
journal, and is posted only after human review.

## What it does

- Accepts JPEG, PNG, and PDF receipts or invoices up to 10 MB.
- Stores private source files in S3-compatible object storage.
- Processes uploads asynchronously with Celery and Redis.
- Extracts structured finance fields through a deterministic mock provider or a
  configurable HTTP AI provider.
- Validates currency, dates, totals, confidence, and required invoice fields.
- Detects identical files and semantic duplicates.
- Suggests an account from a seeded chart of accounts.
- Produces balanced double-entry draft journals.
- Requires owner approval before a journal affects financial summaries.
- Makes upload and posting requests idempotent.
- Shows workflow steps, extraction metadata, decisions, and audit events.
- Enforces tenant scope and database-backed roles on every protected request.

Draft journals are deliberately excluded from posted income, expenses, cash, and
bank balances.

## Run in under five minutes

Prerequisite: Docker Desktop with Docker Compose v2.

```powershell
pnpm dev
```

The command builds and starts Next.js, FastAPI, Celery, PostgreSQL, Redis,
MinIO, and Mailpit. Database migrations and synthetic Kopi Arunika demo data are
applied automatically.

Open [http://localhost:3000](http://localhost:3000) and sign in with:

| Role | Email | Password |
|---|---|---|
| Owner | `owner@kopiarunika.demo` | `Demo123!` |
| Staff | `staff@kopiarunika.demo` | `Demo123!` |

These credentials are for local synthetic data only. Never use them in a public
deployment.

### Demo walkthrough

1. Sign in as the owner.
2. Open **Finance Inbox** and upload `fixtures/sample-receipt.pdf`, or any valid
   PDF, PNG, or JPEG receipt.
3. Watch the status move from queued to review while the page polls the API.
4. Compare the private source preview with the extracted fields.
5. Correct fields if needed, select the suggested ledger account, and save the
   review.
6. Confirm that debit and credit totals match, then approve and post the journal.
7. Open **Ringkasan** to see posted figures and **Approval** or the document
   timeline to inspect the decision history.

The default mock provider returns stable synthetic receipt data, so the complete
workflow works without an external API key.

### Local services

- Web application: http://localhost:3000
- OpenAPI documentation: http://localhost:8000/docs
- System health: http://localhost:8000/api/v1/health
- MinIO console: http://localhost:9001
- Mailpit: http://localhost:8025

Verify the running stack:

```powershell
pnpm dev:verify
```

Stop it with `pnpm dev:down`. To permanently remove this project's local Docker
volumes and rebuild from a clean synthetic seed:

```powershell
pnpm dev:reset
pnpm dev
```

## Configuration

Copy `.env.example` to `.env` to override local defaults.

`AI_PROVIDER=mock` is the safe default. To use a schema-aware external extraction
service, set:

```dotenv
AI_PROVIDER=http
AI_HTTP_ENDPOINT=https://provider.example/v1/extract
AI_HTTP_API_KEY=replace-me
AI_HTTP_MODEL=finance-document-extractor
```

The HTTP adapter sends the private document as base64 together with the required
JSON Schema. Use only a provider and data-processing arrangement appropriate for
your documents. Provider output is always validated before it can create a draft
journal.

## Quality checks

Install dependencies:

```powershell
pnpm install
uv sync --project apps/api --extra dev
```

Run linting, type checking, unit tests, and the production build:

```powershell
pnpm quality
```

The backend suite covers authentication, tenant boundaries, valid and invalid
uploads, schema failures, exact and semantic duplicates, balanced journals,
rejection of unbalanced journals, draft exclusion, audit events, and idempotent
posting.

Useful individual commands:

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm api:migrate
pnpm api:seed
pnpm api:dev
```

When the API runs outside Compose, point `DATABASE_URL`, Redis, and MinIO to
their host ports. The defaults are PostgreSQL `5433` and Redis `6380`;
containers communicate internally through `5432` and `6379`.

## Repository structure

```text
apps/
  api/                 FastAPI, workflows, ledger, Alembic, and tests
  web/                 Next.js inbox, review, approval, and dashboard
services/
  worker/              Celery image using the shared API package
packages/
  contracts/           Space for generated OpenAPI client contracts
infra/
  docker-compose.yml   PostgreSQL, Redis, MinIO, Mailpit, API, worker, and web
fixtures/              Synthetic document inputs
evals/                 Extraction evaluation datasets and runners
docs/
  architecture.md
```

## Security and accounting controls

- JWT claims identify the user and business, while active membership and role
  are rechecked against the database.
- Object keys are tenant-prefixed and source files remain private.
- File signatures are checked instead of trusting extensions or MIME headers.
- Document content is treated as untrusted data; embedded instructions are
  ignored and cannot invoke tools.
- Financial math uses decimal values and deterministic rules.
- Drafts never affect posted financial summaries.
- Posted journals are immutable through the document review flow.
- Owner-only approval and posting are enforced by the API.
- Upload and posting idempotency prevent repeated requests from duplicating
  business records.
- Structured logs and append-only audit events carry correlation IDs without
  exposing source document contents.
- The API and worker containers run as non-root users.
- Production schema changes use Alembic migrations.

See [docs/architecture.md](./docs/architecture.md) for the system flow and trust
boundaries.

## Product boundaries

The application does not initiate payments or bank transfers, file taxes, send
external messages, or connect directly to bank accounts. AI proposes structured
data; deterministic controls and a human owner decide what is posted.
