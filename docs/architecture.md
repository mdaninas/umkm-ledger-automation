# System Architecture

```mermaid
flowchart LR
    Browser["Next.js finance workspace"] --> API["FastAPI"]
    API --> DB[("PostgreSQL")]
    API --> Storage[("Private MinIO bucket")]
    API --> Queue[("Redis")]
    Queue --> Worker["Celery document worker"]
    Worker --> Storage
    Worker --> Provider["Mock or HTTP extraction provider"]
    Worker --> DB
    API --> Match["Deterministic reconciliation engine"]
    Match --> DB
    Beat["Celery daily scheduler"] --> API
    Worker --> Outbox["Approved email outbox"]
    Outbox --> Mailpit["Local Mailpit sandbox"]
    Owner["Business owner"] --> Browser
```

## Document flow

1. The API authenticates the user, validates the file signature, writes it to a
   tenant-prefixed private object key, and stores document metadata.
2. The API returns the document identifier before background extraction starts.
3. Celery records each workflow step, validates structured provider output, runs
   deterministic finance checks, and searches for duplicates.
4. A valid document becomes a balanced draft journal and an approval request.
5. The owner reviews the extracted fields and account category.
6. An idempotent posting transaction marks the journal final and updates the
   financial summary.

## Bank reconciliation flow

1. The user uploads a UTF-8 CSV and explicitly maps date, description, amount,
   and optional reference columns.
2. Each valid row receives a deterministic fingerprint. Duplicate files and
   duplicate transaction rows do not create new records.
3. Read-only bank transactions are compared with posted documents using amount
   (50 points), date distance (20), normalized counterparty (20), and reference
   evidence (10).
4. A conflict-free score of 90 or more may auto-match. Scores from 70 to 89 are
   suggestions; lower scores remain unmatched.
5. Manual confirmation and rejection are tenant-scoped, audited, and protected
   by database constraints that allow only one active match per bank transaction
   and source document.

## Invoice collection flow

1. The daily Celery schedule evaluates each invoice against the calendar date
   in its business timezone.
2. Deterministic rules assign outstanding, due-soon, overdue, or paid status.
3. An overdue invoice receives at most one active reminder. AI assistance may
   supply optional copy, while invoice number, total, currency, and due date are
   rendered directly from database fields.
4. If copy assistance fails, a deterministic template creates the same factual
   draft. The draft remains editable and cannot create an outbox message before
   owner approval.
5. Approval atomically creates one email outbox row with a stable idempotency
   key. Celery delivers it to the local Mailpit sandbox.
6. Sent state, cooldown rules, and the unique outbox key prevent routine retries
   from producing duplicate reminders. Drafting, edits, decisions, failures, and
   delivery are recorded as audit events.

## Trust boundaries

- `business_id` scopes all finance entities and queries.
- JWT business and user claims are insufficient on their own; membership and role
  are loaded from the database.
- Uploaded bytes and extracted text are untrusted input.
- Provider output must match a strict schema and pass deterministic validation.
- The extraction provider cannot post journals or execute tools.
- Source files stay private and are fetched through an authenticated API endpoint.
- Only posted, balanced journals contribute to dashboard totals.
- Bank imports never move money and imported transactions remain read-only.
- Reconciliation scores are deterministic and expose their component evidence.
- Invoice facts are never calculated by the copy provider.
- External delivery requires an approved reminder; public APIs expose only a
  masked recipient.
- Local Mailpit is a demo sandbox, not a production email integration.
- Audit events record system steps and human decisions with correlation IDs.

## Runtime

The API, worker, scheduler, and seed share the same Python package. Alembic owns
production schema changes, while direct schema creation is restricted to
isolated SQLite tests. Health checks cover PostgreSQL, Redis, private object
storage, the worker, and the web application.
