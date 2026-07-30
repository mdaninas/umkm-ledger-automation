#!/usr/bin/env sh
set -eu

curl --fail --silent http://localhost:8000/api/v1/health |
  grep --quiet '"status":"healthy"'

TOKEN="$(
  curl --fail --silent \
    -H "Content-Type: application/json" \
    -d '{"email":"owner@kopiarunika.demo","password":"Demo123!"}' \
    http://localhost:8000/api/v1/auth/login |
    python -c "import json,sys; print(json.load(sys.stdin)['access_token'])"
)"

curl --fail --silent \
  -H "Authorization: Bearer ${TOKEN}" \
  http://localhost:8000/api/v1/auth/me |
  grep --quiet '"name":"Kopi Arunika"'

curl --fail --silent \
  -H "Authorization: Bearer ${TOKEN}" \
  http://localhost:8000/api/v1/bank-transactions |
  grep --quiet '"counts"'

curl --fail --silent \
  -H "Authorization: Bearer ${TOKEN}" \
  http://localhost:8000/api/v1/invoices |
  grep --quiet '"counts"'

curl --fail --silent http://localhost:3000/login >/dev/null

echo "OK: readiness, login demo, tenant, bank, piutang, dan web terverifikasi."
