$ErrorActionPreference = "Stop"

$health = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health"
if ($health.status -ne "healthy") {
    throw "Readiness API belum sehat."
}

$loginBody = @{
    email = "owner@kopiarunika.demo"
    password = "Demo123!"
} | ConvertTo-Json

$session = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/auth/login" `
    -Method Post `
    -ContentType "application/json" `
    -Body $loginBody

$headers = @{ Authorization = "Bearer $($session.access_token)" }
$profile = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/auth/me" `
    -Headers $headers

if ($profile.business.name -ne "Kopi Arunika" -or $profile.role -ne "owner") {
    throw "Profil demo tidak sesuai seed."
}

$accounts = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/accounts" `
    -Headers $headers

if ($accounts.Count -lt 13) {
    throw "Chart of accounts demo belum lengkap."
}

$inbox = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/documents" `
    -Headers $headers

$summary = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/dashboard/summary" `
    -Headers $headers

if ($null -eq $inbox.total -or $null -eq $summary.posted_journal_count) {
    throw "Finance Inbox atau ringkasan ledger belum siap."
}

$web = Invoke-WebRequest -Uri "http://localhost:3000/login" -UseBasicParsing
if ($web.StatusCode -ne 200) {
    throw "Web belum sehat."
}

Write-Host "OK: seluruh komponen readiness sehat."
Write-Host "OK: login owner dan tenant Kopi Arunika terverifikasi."
Write-Host "OK: chart of accounts, Finance Inbox, dan ringkasan ledger siap."
Write-Host "OK: web login merespons HTTP 200."
