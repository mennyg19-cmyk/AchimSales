# Emergency-only deployment to Azure App Service via the shared runtime artifact.
# Normal production delivery is a push to main. Azure starts startup.sh, which
# supervises gunicorn wsgi:application and web.jobs.worker_main as siblings.
#
# Usage:
#   .\deploy.ps1   # build zip, deploy, wait for site to restart

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

python -m pytest tools/test_build_runtime_artifact.py -q --noconftest
if ($LASTEXITCODE -ne 0) { throw "runtime artifact tests failed (exit $LASTEXITCODE)" }

$zipPath = Join-Path $scriptDir "app.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
python tools/build_runtime_artifact.py --zip $zipPath
if ($LASTEXITCODE -ne 0) { throw "runtime artifact build failed (exit $LASTEXITCODE)" }

$zipSize = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host "Built app.zip ($zipSize MB)" -ForegroundColor DarkGray

Write-Host "Deploying to Azure App Service (achim-sales-reports)..." -ForegroundColor Cyan
az webapp deploy --name achim-sales-reports --resource-group AchimReportsApp --type zip --src-path $zipPath
if ($LASTEXITCODE -ne 0) { throw "az webapp deploy failed (exit $LASTEXITCODE)" }

Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Write-Host "Done! Live at https://reports.achimonline.com" -ForegroundColor Green