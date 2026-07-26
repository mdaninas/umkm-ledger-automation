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

$web = Invoke-WebRequest -Uri "http://localhost:3000/login" -UseBasicParsing
if ($web.StatusCode -ne 200) {
    throw "Web belum sehat."
}

Write-Host "OK: seluruh komponen readiness sehat."
Write-Host "OK: login owner dan tenant Kopi Arunika terverifikasi."
Write-Host "OK: web login merespons HTTP 200."
