# Emergency zip deploy to Azure App Service. Prefer the GitHub Action on
# webapp-cache. This script runs the same local checks CI does, then zips
# the same allowlist (tools/build_artifact.py).
#
# Usage:
#   .\deploy.ps1

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$py = $null
foreach ($candidate in @("python", "py")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $py = $candidate
        break
    }
}
if (-not $py) { throw "python is required (same as CI)" }

if (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location (Join-Path $scriptDir "v3")
    try {
        npm ci
        npx tsc --noEmit
        if ($LASTEXITCODE -ne 0) { throw "tsc --noEmit failed" }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    } finally {
        Pop-Location
    }
    git diff --exit-code -- v3/web/static_dist/
    if ($LASTEXITCODE -ne 0) { throw "v3/web/static_dist does not match npm run build" }
}

$env:PYTHONPATH = $scriptDir
& $py -m pytest v3/tests tests -q --tb=short
if ($LASTEXITCODE -ne 0) { throw "pytest failed (exit $LASTEXITCODE)" }

$zipPath = Join-Path $scriptDir "app.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

& $py (Join-Path $scriptDir "tools\build_artifact.py") --zip $zipPath
if ($LASTEXITCODE -ne 0) { throw "build_artifact.py failed" }

$zipSize = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host "Built app.zip ($zipSize MB) from tools/artifact-allowlist.txt"

Write-Host "Deploying to Azure App Service (achim-sales-reports)..."
az webapp deploy --name achim-sales-reports --resource-group AchimReportsApp --type zip --src-path $zipPath
if ($LASTEXITCODE -ne 0) { throw "az webapp deploy failed (exit $LASTEXITCODE)" }

Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

$health = Invoke-WebRequest -Uri "https://reports.achimonline.com/healthz" -UseBasicParsing
if ($health.StatusCode -ne 200) { throw "/healthz returned $($health.StatusCode)" }
Write-Host "Smoke: /healthz $($health.StatusCode)"
Write-Host "Done. Live at https://reports.achimonline.com"
