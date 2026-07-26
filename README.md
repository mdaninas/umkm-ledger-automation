# UMKM Finance Autopilot

**UMKM** stands for *Usaha Mikro, Kecil, dan Menengah*, the Indonesian term for
micro, small, and medium enterprises (MSMEs). These businesses form a vital part
of Indonesia's economy, but many still manage receipts, invoices, bank
transactions, and financial reports through fragmented manual processes.

UMKM Finance Autopilot is a financial automation foundation designed to turn
those scattered inputs into controlled, traceable workflows. It is built
according to the UMKM Finance Autopilot PRD, with deterministic financial rules,
human approval, tenant isolation, and auditability as core principles.

The current implementation intentionally stops at **Phase 0**. Document uploads,
AI extraction, the double-entry ledger, approvals, and other financial actions
are not implemented yet.

## Run in under five minutes

Prerequisite: Docker Desktop with Docker Compose v2.

```powershell
pnpm dev
```

This command builds and starts Next.js, FastAPI, Celery, PostgreSQL, Redis,
MinIO, and Mailpit. Database migrations and demo data seeding run automatically
before the API starts.

Local services:

- Web application: http://localhost:3000
- OpenAPI documentation: http://localhost:8000/docs
- System health: http://localhost:8000/api/v1/health
- MinIO console: http://localhost:9001
- Mailpit: http://localhost:8025

Synthetic demo accounts:

| Role | Email | Password |
|---|---|---|
| Owner | `owner@kopiarunika.demo` | `Demo123!` |
| Staff | `staff@kopiarunika.demo` | `Demo123!` |

Do not use these credentials in a public deployment. To customize the local
configuration, copy `.env.example` to `.env` and replace the default values.

### Verify the stack

After all containers are healthy, run:

```powershell
pnpm dev:verify
```

The verification script checks dependency readiness, owner authentication,
the Kopi Arunika tenant, and the web response.

Stop the stack with:

```powershell
pnpm dev:down
```

To delete the local Docker volumes and recreate the database from a clean seed:

```powershell
pnpm dev:reset
pnpm dev
```

> `pnpm dev:reset` permanently removes the local Docker volumes for this project.

## Local quality gates

Install the dependencies:

```powershell
pnpm install
uv sync --project apps/api --extra dev
```

Run linting, type checking, unit tests, and the production build:

```powershell
pnpm quality
```

Individual commands:

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

To run migrations, seed data, and the API outside Docker:

```powershell
pnpm api:migrate
pnpm api:seed
pnpm api:dev
```

When running the API outside Compose, ensure `DATABASE_URL`, Redis, and MinIO
point to the correct host. The default host ports are PostgreSQL `5433` and
Redis `6380`; containers communicate internally through ports `5432` and `6379`.

## Repository structure

```text
apps/
  api/                 FastAPI, domain foundation, Alembic, and tests
  web/                 Next.js, Tailwind CSS, TanStack Query, and Vitest
services/
  worker/              Celery image using the shared API package
packages/
  contracts/           Reserved for the generated OpenAPI client in MVP 1
infra/
  docker-compose.yml   PostgreSQL, Redis, MinIO, Mailpit, API, worker, and web
fixtures/              Synthetic data for future MVPs
evals/                 Evaluation datasets and runners for future phases
docs/
  architecture.md
```

## Phase 0 security decisions

- JWTs carry user and business identifiers, but membership and role are always
  verified against the database.
- The idempotent seed contains only synthetic Kopi Arunika data.
- Successful logins create audit events with correlation IDs.
- API logs use structured JSON, while generic error responses do not expose
  stack traces.
- Production schemas are changed exclusively through Alembic migrations.
- Readiness checks cover the API, database, Redis, MinIO, and Celery worker.
- The API and worker containers run as non-root users.
- No transfers, payments, external messages, or other financial actions exist
  in Phase 0.

See [docs/architecture.md](./docs/architecture.md) for the architecture diagram
and Phase 0 boundaries.

## Phase 0 exit gate

| PRD gate | Evidence |
|---|---|
| All services are healthy | Compose health checks and `pnpm dev:verify` |
| Demo login succeeds | API tests and stack verification |
| Migration and seed work from an empty database | `migrate` service and seed idempotency test |
| Baseline tests pass | `pnpm quality` and the GitHub Actions workflow |

MVP 1 should only begin after Phase 0 has been reviewed and approved.
