# UMKM Finance Autopilot

Foundation aplikasi automation keuangan untuk UMKM berdasarkan
[PRD](../PRD_UMKM_Finance_Autopilot.md). Implementasi saat ini sengaja berhenti di
**Fase 0**: belum ada upload dokumen, ekstraksi AI, ledger, atau tindakan finansial.

## Jalankan dalam kurang dari lima menit

Prasyarat: Docker Desktop dengan Compose v2.

```powershell
pnpm dev
```

Perintah itu membangun dan menjalankan Next.js, FastAPI, Celery, PostgreSQL, Redis,
MinIO, serta Mailpit. Migration dan seed dijalankan otomatis sebelum API dimulai.

Buka:

- Web: http://localhost:3000
- OpenAPI: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- MinIO console: http://localhost:9001
- Mailpit: http://localhost:8025

Akun sintetis demo:

| Role | Email | Password |
|---|---|---|
| Owner | `owner@kopiarunika.demo` | `Demo123!` |
| Staff | `staff@kopiarunika.demo` | `Demo123!` |

Jangan gunakan kredensial ini di deployment publik. Nilai lokal dapat diganti dengan
menyalin `.env.example` menjadi `.env`.

### Verifikasi stack

Setelah seluruh container sehat:

```powershell
pnpm dev:verify
```

Script memeriksa readiness seluruh dependency, login owner, tenant Kopi Arunika, dan
respons web. Hentikan stack dengan `pnpm dev:down`. Untuk reset database dan seed dari
nol gunakan `pnpm dev:reset`, lalu `pnpm dev` lagi.

## Quality gates lokal

Instal dependency:

```powershell
pnpm install
uv sync --project apps/api --extra dev
```

Jalankan seluruh lint, type-check, unit test, dan build:

```powershell
pnpm quality
```

Perintah individual:

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Migration dan seed saat menjalankan API di luar Docker:

```powershell
pnpm api:migrate
pnpm api:seed
pnpm api:dev
```

Pastikan `DATABASE_URL`, Redis, dan MinIO mengarah ke host yang benar bila API
dijalankan di luar Compose. Port host default adalah PostgreSQL `5433` dan Redis
`6380`; komunikasi internal container tetap menggunakan `5432` dan `6379`.

## Struktur repository

```text
apps/
  api/                 FastAPI, domain foundation, Alembic, tests
  web/                 Next.js, Tailwind CSS, TanStack Query, Vitest
services/
  worker/              Image Celery dengan package API bersama
packages/
  contracts/           Tempat generated OpenAPI client pada MVP 1
infra/
  docker-compose.yml   PostgreSQL, Redis, MinIO, Mailpit, API, worker, web
fixtures/              Data sintetis untuk MVP berikutnya
evals/                 Dataset dan runner evaluasi untuk fase berikutnya
docs/
  architecture.md
```

## Keputusan keamanan Fase 0

- JWT membawa ID pengguna dan ID bisnis, tetapi membership dan role selalu
  diverifikasi kembali dari database.
- Seed bersifat idempotent dan hanya berisi data sintetis Kopi Arunika.
- Login sukses dicatat sebagai audit event dengan correlation ID.
- Log API berbentuk JSON dan respons error umum tidak menampilkan stack trace.
- Schema production hanya diubah melalui Alembic.
- Readiness memeriksa API, database, Redis, MinIO, dan Celery worker.
- Tidak ada transfer, pembayaran, external messaging, atau fitur finansial lain.

Diagram dan batas arsitektur tersedia di
[docs/architecture.md](./docs/architecture.md).

## Exit gate Fase 0

| Gate PRD | Bukti |
|---|---|
| Seluruh service sehat | Compose healthcheck + `pnpm dev:verify` |
| Login demo berhasil | Test API dan verifikasi stack |
| Migration/seed dari database kosong | Service `migrate`, seed idempotency test |
| Test dasar lulus | `pnpm quality` dan workflow GitHub Actions |

MVP 1 baru boleh dimulai setelah Fase 0 ini ditinjau dan disetujui.
