# Deploy to Azure App Service
# Usage: .\deploy.ps1          (fast / code-only - keeps existing virtualenv)
#        .\deploy.ps1 --build   (full build with pip install)

$ErrorActionPreference = "Stop"
$APP_NAME = "achim-sales-reports"
$RG = "AchimReportsApp"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$totalTimer = [System.Diagnostics.Stopwatch]::StartNew()

# ── Step 1: Build zip ────────────────────────────────────────────────────
Write-Host "Building deployment package..." -ForegroundColor Cyan
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

$zipPath = Join-Path $env:TEMP "achim_deploy.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

$exclude = @(
    ".env", ".env.example", "app.zip", "deploy.ps1", "deploy-cache.ps1",
    ".azure", ".git", ".gitignore", ".pytest_cache",
    "tests", "logs", "runbooks", "SETUP_INSTRUCTIONS.txt",
    "_history_backup", "_report_output", "__pycache__",
    "app.db", "AchimReportsApp.zip", "app_v2.py",
    "webapp-cache", "webapp_v2"
)
$excludeExt = @(".md", ".pyc")

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

    $webappReq = Join-Path $scriptDir "webapp\requirements.txt"
    if (Test-Path $webappReq) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $webappReq, "requirements.txt") | Out-Null
    }
}
finally {
    $zip.Dispose()
}

$zipSize = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)
$zipElapsed = [math]::Round($stepTimer.Elapsed.TotalSeconds, 1)
Write-Host "  Zip created: ${zipSize}MB (${zipElapsed}s)" -ForegroundColor DarkGray

# ── Step 2: Deploy ───────────────────────────────────────────────────────
$doBuild = $args -contains "--build"

if ($doBuild) {
    Write-Host "`nDeploying to Azure (with remote build)..." -ForegroundColor Cyan
    Write-Host "  This will run pip install -- expect 3-6 min" -ForegroundColor DarkGray
    $stepTimer.Restart()

    az webapp config appsettings set `
        --name $APP_NAME --resource-group $RG `
        --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true `
        --output none 2>$null

    az webapp deployment source config-zip `
        --name $APP_NAME --resource-group $RG `
        --src $zipPath --timeout 600

    $elapsed = [math]::Round($stepTimer.Elapsed.TotalSeconds, 1)
    Write-Host "  Build deploy finished (${elapsed}s)" -ForegroundColor DarkGray
} else {
    Write-Host "`nDeploying to Azure (code-only / no build)..." -ForegroundColor Cyan
    $stepTimer.Restart()

    az webapp config appsettings set `
        --name $APP_NAME --resource-group $RG `
        --settings SCM_DO_BUILD_DURING_DEPLOYMENT=false `
        --output none 2>$null

    $ErrorActionPreference = "Continue"
    az webapp deploy `
        --name $APP_NAME --resource-group $RG `
        --src-path $zipPath --type zip --async true 2>&1 | Out-String | Write-Host
    $ErrorActionPreference = "Stop"

    $elapsed = [math]::Round($stepTimer.Elapsed.TotalSeconds, 1)
    Write-Host "  Deploy kicked off (${elapsed}s)" -ForegroundColor DarkGray
    Write-Host "  Tip: run .\deploy.ps1 --build if you changed requirements.txt" -ForegroundColor DarkGray
}

# ── Step 3: Restart the app ─────────────────────────────────────────────
Write-Host "`nRestarting app..." -ForegroundColor Cyan
az webapp restart --name $APP_NAME --resource-group $RG --output none 2>$null
Write-Host "  App restarted." -ForegroundColor DarkGray

# ── Cleanup ──────────────────────────────────────────────────────────────
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $scriptDir "app.zip") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $scriptDir "AchimReportsApp.zip") -Force -ErrorAction SilentlyContinue

$totalElapsed = [math]::Round($totalTimer.Elapsed.TotalSeconds, 1)
Write-Host "`nDone! Total: ${totalElapsed}s" -ForegroundColor Green
