# Flip reports.achimonline.com between Flask and FastAPI.
# Azure App Settings and Startup Command stay as they are.
#
#   double-click switch-site.bat
#   .\switch-site.ps1
#   .\switch-site.ps1 fastapi
#   .\switch-site.ps1 flask
#   .\switch-site.ps1 status
#   .\switch-site.ps1 fastapi -WhatIf
#
# This script does git + the GitHub deploy Action. Snapshot / import still
# run in Azure SSH (that box's /tmp). The script copies those commands and waits.

param(
    [Parameter(Position = 0)]
    [string]$To = "",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$SiteUrl = "https://reports.achimonline.com"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step($text) { Write-Host $text -ForegroundColor Cyan }
function Write-Warn($text) { Write-Host $text -ForegroundColor Yellow }
function Fail($text) { throw $text }

function Invoke-Git {
    param([string[]]$GitArgs)
    Write-Host ("> git " + ($GitArgs -join " ")) -ForegroundColor DarkGray
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) { Fail "git $($GitArgs[0]) failed (exit $LASTEXITCODE)." }
}

function Get-NewestTag([string]$Prefix) {
    $names = @(git tag -l "$Prefix*")
    if (-not $names) { return $null }
    return ($names | Sort-Object | Select-Object -Last 1)
}

function Get-MainStack {
    $top = @(git ls-tree --name-only origin/main)
    if ($top -contains "wsgi.py") { return "flask" }
    if ($top -contains "main.py") { return "fastapi" }
    return "unknown"
}

function Get-LiveAssetV {
    try {
        $html = (Invoke-WebRequest -Uri $SiteUrl -UseBasicParsing -TimeoutSec 30).Content
    } catch {
        return $null
    }
    if ($html -match 'main\.css\?v=([^"&\s]+)') { return $Matches[1] }
    return $null
}

function Stack-FromAsset([string]$AssetV) {
    if (-not $AssetV) { return "unknown" }
    if ($AssetV -match '^home\d+$') { return "fastapi" }
    if ($AssetV -match '^\d+$') { return "flask" }
    return "unknown"
}

function Show-Status {
    $asset = Get-LiveAssetV
    $live = Stack-FromAsset $asset
    $main = Get-MainStack
    $flaskTag = Get-NewestTag "flask-prod-"
    $fastapiTag = Get-NewestTag "fastapi-rebuild-parked-"
    Write-Host ""
    Write-Host "Live site  $SiteUrl"
    if ($asset) {
        Write-Host ("  CSS ?v=$asset  ->  $live")
    } else {
        Write-Host "  (could not read main.css — check the login page yourself)"
    }
    Write-Host "origin/main git tree  ->  $main"
    Write-Host "Flask tag     $flaskTag"
    Write-Host "FastAPI tag   $fastapiTag"
    Write-Host ""
    return [pscustomobject]@{
        Live     = $live
        Asset    = $asset
        Main     = $main
        Flask    = $flaskTag
        Fastapi  = $fastapiTag
    }
}

function Wait-Enter([string]$Prompt) {
    Write-Host ""
    Write-Warn $Prompt
    Read-Host "Press Enter to continue (Ctrl+C to abort)" | Out-Null
}

function Copy-And-Show([string]$Title, [string]$Commands) {
    Write-Host ""
    Write-Host $Title -ForegroundColor Yellow
    Write-Host "---- paste in Azure SSH (App Service -> SSH, not Kudu Bash) ----"
    Write-Host $Commands
    Write-Host "----------------------------------------------------------------"
    try {
        Set-Clipboard -Value $Commands
        Write-Host "(copied to clipboard)" -ForegroundColor DarkGray
    } catch {
        Write-Host "(could not copy clipboard — copy from above)" -ForegroundColor DarkGray
    }
}

$SnapshotFlask = @'
printenv BETA_PRECIOUS_DB_PATH
ls -lh "${BETA_PRECIOUS_DB_PATH:-/tmp/betadata/precious.db}" /home/LogFiles/home-precious.db
python3 -c "import os,sqlite3; s=sqlite3.connect('file:'+(os.environ.get('BETA_PRECIOUS_DB_PATH') or '/tmp/betadata/precious.db')+'?mode=ro', uri=True); d=sqlite3.connect('/home/LogFiles/home-precious.db'); s.backup(d); s.close(); d.close(); print('copied to /home/LogFiles/home-precious.db')"
ls -lh /home/LogFiles/home-precious.db
'@

$ImportFastapi = @'
cd /home/site/wwwroot
python3 import-precious.py /home/LogFiles/home-precious.db --dest /tmp/homedata/home.sqlite
'@

$RestoreFlask = @'
printenv BETA_PRECIOUS_DB_PATH
ls -lh "${BETA_PRECIOUS_DB_PATH:-/tmp/betadata/precious.db}" /home/LogFiles/home-precious.db
python3 -c "import os,sqlite3; p=os.environ.get('BETA_PRECIOUS_DB_PATH') or '/tmp/betadata/precious.db'; os.makedirs(os.path.dirname(p), exist_ok=True); s=sqlite3.connect('file:/home/LogFiles/home-precious.db?mode=ro', uri=True); d=sqlite3.connect(p); s.backup(d); s.close(); d.close(); print('restored', p)"
'@

function Confirm-Switch([string]$Target) {
    Write-Host ""
    Write-Warn "This pushes to main and deploys $Target to $SiteUrl."
    Write-Warn "Type SWITCH to continue."
    $answer = Read-Host "Confirm"
    if ($answer -ne "SWITCH") { Fail "Aborted (type SWITCH in all caps to run)." }
}

function Assert-Clean {
    $status = @(git status --porcelain)
    if ($status) {
        Write-Host ($status -join "`n")
        Fail "Working tree is dirty. Commit or stash, then run this again."
    }
}

function Switch-MainToTag([string]$Tag, [string]$Message) {
    Assert-Clean
    Invoke-Git -GitArgs @("fetch", "origin", "--tags")
    Invoke-Git -GitArgs @("fetch", "origin", "main")
    $want = & git rev-parse "$Tag^{tree}"
    if ($LASTEXITCODE -ne 0 -or -not $want) { Fail "Tag $Tag not found. git fetch origin --tags and check CUTOVER.md." }
    Invoke-Git -GitArgs @("checkout", "main")
    Invoke-Git -GitArgs @("pull", "--ff-only", "origin", "main")
    Assert-Clean
    $have = & git rev-parse "HEAD^{tree}"
    if ($have -eq $want) {
        Write-Host "main already has $Tag's tree. Nothing to push."
        return $false
    }
    Invoke-Git -GitArgs @("read-tree", "-u", "--reset", $Tag)
    Invoke-Git -GitArgs @("commit", "-m", $Message)
    Invoke-Git -GitArgs @("push", "origin", "main")
    return $true
}

function Watch-Deploy([string]$HeadSha) {
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) {
        Write-Warn "GitHub CLI (gh) is not on PATH. Open https://github.com/mennyg19-cmyk/AchimSales/actions and wait for the main deploy to go green."
        Wait-Enter "Press Enter after that Action is success (red = stop, do not Restart Azure)."
        return
    }
    Write-Step "Waiting for the main deploy Action..."
    $runId = $null
    foreach ($i in 1..24) {
        $json = gh run list --branch main --limit 5 --json databaseId,headSha,status,conclusion,url,displayTitle 2>$null
        if ($LASTEXITCODE -eq 0 -and $json) {
            $runs = $json | ConvertFrom-Json
            $match = $runs | Where-Object { $_.headSha -eq $HeadSha } | Select-Object -First 1
            if ($match) {
                $runId = $match.databaseId
                Write-Host $match.url
                break
            }
        }
        Start-Sleep -Seconds 5
    }
    if (-not $runId) {
        Write-Warn "Could not find the new Action run yet. Watch it in the browser."
        Start-Process "https://github.com/mennyg19-cmyk/AchimSales/actions" -ErrorAction SilentlyContinue
        Wait-Enter "Press Enter after the Action is success."
        return
    }
    gh run watch $runId --exit-status
    if ($LASTEXITCODE -ne 0) { Fail "Deploy Action failed. Do not Restart Azure to nudge it. Fix the Action first." }
    Write-Host "Deploy Action is green." -ForegroundColor Green
}

function Wait-Live([string]$WantStack) {
    Write-Step "Waiting for gunicorn to recycle (CSS should become $WantStack)..."
    foreach ($i in 1..12) {
        Start-Sleep -Seconds 15
        $asset = Get-LiveAssetV
        $live = Stack-FromAsset $asset
        Write-Host ("  try $i  ?v=$asset  ->  $live") -ForegroundColor DarkGray
        if ($live -eq $WantStack) {
            Write-Host "Live site is $WantStack." -ForegroundColor Green
            return
        }
    }
    Write-Warn "Action was green but the login CSS is not $WantStack yet. Hard-refresh. Wait another minute if it is still the old ?v=."
}

if ($To -eq "") {
    $To = Read-Host "Switch production to fastapi, flask, or status?"
}
$To = $To.Trim().ToLower()
if ($To -in @("q", "quit", "exit")) { return }
if ($To -in @("fastapi", "fast", "a")) { $To = "fastapi" }
elseif ($To -in @("flask", "b")) { $To = "flask" }
elseif ($To -in @("status", "s", "what")) { $To = "status" }
else { Fail "Usage: .\switch-site.ps1 fastapi | flask | status" }

Write-Step "Fetching tags and origin/main..."
Invoke-Git -GitArgs @("fetch", "origin", "--tags")
Invoke-Git -GitArgs @("fetch", "origin", "main")
$status = Show-Status

if ($To -eq "status") { return }

$tag = if ($To -eq "fastapi") { $status.Fastapi } else { $status.Flask }
if (-not $tag) { Fail "No $To tag found. See CUTOVER.md (flask-prod-* / fastapi-rebuild-parked-*)." }

Write-Host "Target: $To   tag: $tag"
if ($status.Main -eq $To) {
    Write-Warn "origin/main is already $To. Running this would still be a no-op if that tag matches main."
}

if ($WhatIf) {
    Write-Host "[WhatIf] Would snapshot/import via Azure SSH, then:"
    Write-Host "  git checkout main; git read-tree -u --reset $tag; commit; push origin main"
    return
}

Confirm-Switch $To

if ($To -eq "fastapi") {
    Copy-And-Show "1/2 Azure: snapshot Flask home sqlite (must be much larger than 620K)." $SnapshotFlask
    Wait-Enter "Press Enter after ls shows a large /home/LogFiles/home-precious.db (not ~620K)."
} else {
    Write-Host "Flask does not read home.sqlite. Leave that file alone."
}

Write-Step "Replacing main's tree with $tag..."
$pushed = Switch-MainToTag $tag "Switch production to $(if ($To -eq 'fastapi') { 'FastAPI' } else { 'Flask' })."
if ($pushed) {
    $head = git rev-parse HEAD
    Watch-Deploy $head
} else {
    Write-Host "Skipped deploy watch (tree already matched)."
}

Wait-Live $To
Start-Process $SiteUrl -ErrorAction SilentlyContinue

if ($To -eq "fastapi") {
    Copy-And-Show "2/2 Azure: only if People is empty or Entra 403s. Last line must say into /tmp/homedata/home.sqlite" $ImportFastapi
    Write-Warn "Wait a minute for Litestream after import. Do not Azure Restart before that copy exists."
} else {
    Copy-And-Show "Azure: only if People / views look empty. Not /tmp/v3data." $RestoreFlask
    Write-Warn "Do not Azure Restart until that restore ran if the replica did not come back."
}

Write-Host ""
Write-Host "Hard-refresh $SiteUrl"
Write-Host "Flask CSS is a number. FastAPI CSS is home13 (or later homeN)."
Write-Host "Done. Full notes: CUTOVER.md"
