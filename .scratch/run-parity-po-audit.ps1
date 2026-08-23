# Parity ordered + invoiced after cookies are set in .scratch/parity-cookies.env
# File format (no quotes):
#   PARITY_LIVE_COOKIE=...
#   PARITY_TEST_COOKIE=...
#   PARITY_BASE_URL=https://reports.achimonline.com
$ErrorActionPreference = "Stop"
Set-Location "D:\Projects\Achim\AchimSales"

$cookieFile = ".scratch/parity-cookies.env"
if (-not (Test-Path $cookieFile)) { throw "Missing $cookieFile" }
Get-Content $cookieFile | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
  $k, $v = $_.Split('=', 2)
  Set-Item -Path ("Env:" + $k.Trim()) -Value $v.Trim()
}
if (-not $env:PARITY_BASE_URL) { $env:PARITY_BASE_URL = "https://reports.achimonline.com" }

python .scratch/probe_auth_status.py
if ($LASTEXITCODE -ne 0) { throw "Auth probe failed — refresh cookies" }

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out = ".scratch/parity/$stamp-po-audit-retest"
New-Item -ItemType Directory -Force -Path $out | Out-Null
Write-Output "OUT=$out"

python -m tools.parity `
  --report ordered `
  --report invoiced `
  --out $out -v --timeout 3600
$code = $LASTEXITCODE
Write-Output "PARITY_EXIT=$code"

python .scratch/parity_noise_filter.py $out
Write-Output "DONE"
