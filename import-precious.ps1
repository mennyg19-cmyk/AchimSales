# Copy People, views, and schedules from the old site's precious.db.
#
# Usage:
#   .\import-precious.ps1 -Precious C:\Users\you\Downloads\precious.db
#   .\import-precious.ps1 .\precious.db
#   .\import-precious.ps1 .\precious.db -Dest .\app\data\home.sqlite

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Precious,
    [string]$Dest = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$python = $null
foreach ($name in @("python", "python3", "py")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
        $python = $cmd.Source
        break
    }
}
if (-not $python) {
    throw "Python is not on PATH. Install Python, then run this again."
}

if (-not (Test-Path -LiteralPath $Precious -PathType Leaf)) {
    throw "No file at $Precious. Copy precious.db off the old site first."
}

$preciousFull = (Resolve-Path -LiteralPath $Precious).Path
$script = Join-Path $root "import-precious.py"
$argList = @($script, $preciousFull)
if ($Dest) {
    if ([System.IO.Path]::IsPathRooted($Dest)) {
        $destFull = $Dest
    } else {
        $destFull = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Dest))
    }
    $argList += "--dest"
    $argList += $destFull
}

& $python @argList
if ($LASTEXITCODE -ne 0) {
    throw "Import failed (exit $LASTEXITCODE)."
}
