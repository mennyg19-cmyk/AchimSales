# Deploy the rebuild FastAPI app to a NEW Azure Web App.
# Never the live site (achim-sales-reports / reports.achimonline.com).
#
# Usage (from this folder):
#   .\deploy.ps1 -Name <new-webapp-name>
#
# The zip root is this folder (main.py + requirements.txt + startup.sh),
# which is what Linux App Service / Oryx expects.

param(
    [Parameter(Mandatory = $true)]
    [string]$Name
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$blocked = @("achim-sales-reports")
if ($blocked -contains $Name.ToLowerInvariant()) {
    throw "Refusing to deploy the rebuild onto '$Name'. That is the live site. Create a new Web App first."
}

$zipPath = Join-Path $scriptDir "app.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

$excludeNames = @(
    ".venv", ".pytest_cache", "__pycache__", ".git",
    "tests", "rebuild-reference", "app.zip", "deploy.ps1"
)
$excludeExt = @(".pyc")

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, "Create")
try {
    Get-ChildItem -Path $scriptDir -Recurse -File | Where-Object {
        $rel = $_.FullName.Substring($scriptDir.Length + 1)
        $parts = $rel -split "[\\/]"
        $skip = $false
        foreach ($part in $parts) {
            if ($excludeNames -contains $part) { $skip = $true; break }
        }
        if (-not $skip) {
            foreach ($ext in $excludeExt) {
                if ($_.Extension -eq $ext) { $skip = $true; break }
            }
        }
        -not $skip
    } | ForEach-Object {
        $rel = $_.FullName.Substring($scriptDir.Length + 1)
        $entryName = $rel -replace "\\", "/"
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $entryName) | Out-Null
    }
} finally {
    $zip.Dispose()
}

Write-Host "Built app.zip. Deploying to $Name (not the live site)..."
az webapp deploy --name $Name --resource-group AchimReportsApp --type zip --src-path $zipPath
if ($LASTEXITCODE -ne 0) { throw "az webapp deploy failed (exit $LASTEXITCODE)" }
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
Write-Host "Done. Set Startup Command to: bash /home/site/wwwroot/startup.sh"
