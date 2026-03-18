# Deploy webapp-cache to Azure App Service
# Usage: .\deploy-cache.ps1          (fast / code-only - keeps existing virtualenv)
#        .\deploy-cache.ps1 --build   (full build with pip install)

$ErrorActionPreference = "Stop"
$APP_NAME = "achim-sales-reports"
$RG = "AchimReportsApp"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$cacheDir = Join-Path $scriptDir "webapp-cache"

if (-not (Test-Path $cacheDir)) {
    Write-Host "ERROR: webapp-cache folder not found at $cacheDir" -ForegroundColor Red
    exit 1
}

$totalTimer = [System.Diagnostics.Stopwatch]::StartNew()

# ── Step 1: Build zip ────────────────────────────────────────────────────
Write-Host "Building deployment package from webapp-cache..." -ForegroundColor Cyan
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

$zipPath = Join-Path $env:TEMP "achim_cache_deploy.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

$exclude = @(
    ".env", ".env.example", "deploy-cache.ps1",
    ".azure", ".git", ".gitignore", ".pytest_cache",
    "tests", "logs", "SETUP_INSTRUCTIONS.txt",
    "_history_backup", "_report_output", "__pycache__",
    "app.db", "*.pyc"
)

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, 'Create')

try {
    # Add all webapp-cache files (these go at the zip root as "webapp/...")
    Get-ChildItem -Path $cacheDir -Recurse -File | Where-Object {
        $rel = $_.FullName.Substring($cacheDir.Length + 1)
        $parts = $rel -split '\\'
        $skip = $false
        foreach ($part in $parts) {
            foreach ($ex in $exclude) {
                if ($part -eq $ex -or $_.Extension -eq ".pyc") { $skip = $true; break }
            }
            if ($skip) { break }
        }
        -not $skip
    } | ForEach-Object {
        $rel = $_.FullName.Substring($cacheDir.Length + 1)
        $entryName = "webapp/" + ($rel -replace '\\', '/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $entryName) | Out-Null
    }

    # Add shared dependencies that webapp-cache imports (config/, core/, data/)
    foreach ($sharedDir in @("config", "core", "data")) {
        $sharedPath = Join-Path $scriptDir $sharedDir
        if (Test-Path $sharedPath) {
            Get-ChildItem -Path $sharedPath -Recurse -File | Where-Object {
                $_.Extension -ne ".pyc" -and $_.FullName -notmatch '__pycache__'
            } | ForEach-Object {
                $rel = $_.FullName.Substring($scriptDir.Length + 1)
                $entryName = $rel -replace '\\', '/'
                [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $entryName) | Out-Null
            }
        }
    }

    # Add report_registry.json if present
    $registry = Join-Path $scriptDir "report_registry.json"
    if (Test-Path $registry) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $registry, "report_registry.json") | Out-Null
    }

    # Add app.py at the zip root (Azure needs this for gunicorn)
    # Create a thin shim that imports from webapp.app
    $shimContent = "from webapp.app import app`n"
    $shimPath = Join-Path $env:TEMP "app_shim.py"
    Set-Content -Path $shimPath -Value $shimContent -NoNewline
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $shimPath, "app.py") | Out-Null
    Remove-Item $shimPath -Force

    # Copy requirements.txt to zip root for pip install
    $reqFile = Join-Path $cacheDir "requirements.txt"
    if (Test-Path $reqFile) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $reqFile, "requirements.txt") | Out-Null
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

    az webapp deploy `
        --name $APP_NAME --resource-group $RG `
        --src-path $zipPath --type zip --async true

    $elapsed = [math]::Round($stepTimer.Elapsed.TotalSeconds, 1)
    Write-Host "  Deploy kicked off (${elapsed}s)" -ForegroundColor DarkGray
    Write-Host "  Tip: run .\deploy-cache.ps1 --build if you changed requirements.txt" -ForegroundColor DarkGray
}

# ── Step 3: Restart the app ─────────────────────────────────────────────
Write-Host "`nRestarting app..." -ForegroundColor Cyan
az webapp restart --name $APP_NAME --resource-group $RG --output none 2>$null
Write-Host "  App restarted." -ForegroundColor DarkGray

# ── Cleanup ──────────────────────────────────────────────────────────────
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

$totalElapsed = [math]::Round($totalTimer.Elapsed.TotalSeconds, 1)
Write-Host "`nDone! Total: ${totalElapsed}s" -ForegroundColor Green
