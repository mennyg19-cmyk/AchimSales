[CmdletBinding()]
param(
    [string]$Destination = "C:\Users\Menny\OneDrive - Achim Importing Co., Inc\Achim Importing Co., Inc. Team Site - D365 F&O\scripts",
    [switch]$Prune,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$source = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$destinationPath = [System.IO.Path]::GetFullPath($Destination)

if (-not (Test-Path -LiteralPath $destinationPath)) {
    throw "OneDrive destination does not exist: $destinationPath"
}

if ($source -eq $destinationPath) {
    throw "Source and destination must be different folders."
}

$excludeDirectories = @(
    ".git", ".codegraph", ".scratch", "node_modules", ".next", ".turbo",
    "dist", "build", "coverage", "__pycache__", ".pytest_cache",
    "test-results", "playwright-report", "logs", "_report_output",
    "_history_backup", "outbox"
)
$excludeFiles = @(".env", ".env.*", "*.db", "*.db-shm", "*.db-wal", "*.log", "*.zip")

$arguments = @(
    $source,
    $destinationPath,
    "/E",
    "/COPY:DAT",
    "/DCOPY:DAT",
    "/R:2",
    "/W:2",
    "/XJ",
    "/XD"
) + $excludeDirectories + @("/XF") + $excludeFiles

if ($Prune) {
    $arguments += "/MIR"
}

if ($WhatIf) {
    $arguments += "/L"
}

& robocopy @arguments
if ($LASTEXITCODE -ge 8) {
    throw "OneDrive sync failed with robocopy exit code $LASTEXITCODE."
}

$mode = if ($WhatIf) { "dry run" } elseif ($Prune) { "pruned sync" } else { "sync" }
Write-Host "OneDrive $mode completed." -ForegroundColor Green
exit 0
