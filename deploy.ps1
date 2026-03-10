# Deploy to Azure App Service
# Usage: .\deploy.ps1

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$zipPath = Join-Path $scriptDir "app.zip"

if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

$exclude = @(
    ".env",
    ".env.example",
    "app.zip",
    "deploy.ps1",
    ".azure",
    ".pytest_cache",
    "tests",
    "logs",
    "runbooks",
    "SETUP_INSTRUCTIONS.txt",
    "_history_backup",
    "_report_output",
    "__pycache__",
    "app.db",
    "AchimReportsApp.zip"
)

$excludeExt = @(".md")

Add-Type -AssemblyName System.IO.Compression.FileSystem

$zip = [System.IO.Compression.ZipFile]::Open($zipPath, 'Create')

try {
    Get-ChildItem -Path $scriptDir -Recurse -File | Where-Object {
        $rel = $_.FullName.Substring($scriptDir.Length + 1)
        $parts = $rel -split '\\'
        $skip = $false

        # Check if any path segment matches an excluded name
        foreach ($part in $parts) {
            foreach ($ex in $exclude) {
                if ($part -eq $ex) { $skip = $true; break }
            }
            if ($skip) { break }
        }

        # Check file extension
        if (-not $skip) {
            foreach ($ext in $excludeExt) {
                if ($_.Extension -eq $ext) { $skip = $true; break }
            }
        }

        -not $skip
    } | ForEach-Object {
        $rel = $_.FullName.Substring($scriptDir.Length + 1)
        # Convert Windows backslashes to forward slashes for Linux
        $entryName = $rel -replace '\\', '/'
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $entryName) | Out-Null
    }

    # Copy webapp/requirements.txt to root as well
    $webappReq = Join-Path $scriptDir "webapp\requirements.txt"
    if (Test-Path $webappReq) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $webappReq, "requirements.txt") | Out-Null
    }
}
finally {
    $zip.Dispose()
}

Write-Host "Deploying to Azure..." -ForegroundColor Cyan
az webapp deploy --name achim-sales-reports --resource-group AchimReportsApp --type zip --src-path $zipPath

Write-Host "Done!" -ForegroundColor Green
