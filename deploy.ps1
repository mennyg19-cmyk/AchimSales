# Deploy the webapp to Azure App Service via zip.
# Prod setup: built-in Python 3.10 runtime, gunicorn app:app.
#
# Usage:
#   .\deploy.ps1   # build zip, deploy, wait for site to restart

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$zipPath = Join-Path $scriptDir "app.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

# Files/dirs to keep out of the deployment zip. Anything not in the prod
# runtime path (runbooks/, tests/, local-only tooling, secrets).
$exclude = @(
    ".env", ".env.example", "app.zip",
    "deploy.ps1", "deploy-runbook.ps1",
    ".azure", ".pytest_cache", ".git", ".cursor",
    ".dockerignore", "Dockerfile",
    "tests", "test", "logs", "runbooks", "webapp-cache",
    "SETUP_INSTRUCTIONS.txt",
    "_history_backup", "_report_output", "__pycache__",
    "app.db", "AchimReportsApp.zip", "_server.log"
)
$excludeExt = @(".md")

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, 'Create')
try {
    Get-ChildItem -Path $scriptDir -Recurse -File | Where-Object {
        $rel = $_.FullName.Substring($scriptDir.Length + 1)
        $parts = $rel -split '\\'
        $skip = $false
        foreach ($part in $parts) {
            foreach ($ex in $exclude) {
                if ($part -eq $ex) { $skip = $true; break }
            }
            if ($skip) { break }
        }
        if (-not $skip) {
            foreach ($ext in $excludeExt) {
                if ($_.Extension -eq $ext) { $skip = $true; break }
            }
        }
        -not $skip
    } | ForEach-Object {
        $rel = $_.FullName.Substring($scriptDir.Length + 1)
        $entryName = $rel -replace '\\', '/'
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $entryName) | Out-Null
    }

    # Oryx builder expects requirements.txt at the zip root.
    $webappReq = Join-Path $scriptDir "webapp\requirements.txt"
    if (Test-Path $webappReq) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $webappReq, "requirements.txt") | Out-Null
    }
} finally {
    $zip.Dispose()
}

$zipSize = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host "Built app.zip ($zipSize MB)" -ForegroundColor DarkGray

Write-Host "Deploying to Azure App Service (achim-sales-reports)..." -ForegroundColor Cyan
az webapp deploy --name achim-sales-reports --resource-group AchimReportsApp --type zip --src-path $zipPath
if ($LASTEXITCODE -ne 0) { throw "az webapp deploy failed (exit $LASTEXITCODE)" }

Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Write-Host "Done! Live at https://reports.achimonline.com" -ForegroundColor Green