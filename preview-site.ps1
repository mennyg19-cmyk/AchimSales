# Put the parked FastAPI site on a NEW Azure Web App so you can test
# without touching reports.achimonline.com.
#
#   az login
#   .\preview-site.ps1
#   .\preview-site.ps1 -Name achim-sales-preview
#
# Refuses the live app name. Copies Reporting API + Graph settings from
# production. Does not copy Litestream (preview sqlite is its own file).

param(
    [string]$Name = "achim-sales-preview",
    [string]$ResourceGroup = "",
    [string]$LiveName = "achim-sales-reports",
    [string]$Plan = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ($Name.ToLowerInvariant() -eq $LiveName.ToLowerInvariant()) {
    throw "Refusing to deploy FastAPI onto $LiveName. That is the live Flask site."
}

$az = Get-Command az -ErrorAction SilentlyContinue
if (-not $az) { throw "Azure CLI (az) is not on PATH. Install it, run az login, then this script again." }

function Get-AzText {
    param([string[]]$AzArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $text = az @AzArgs 2>&1 | Out-String
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    return @{ Code = $code; Text = $text.Trim() }
}

function Clear-PreviewWorktree([string]$Path) {
    Set-Location $Root
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    git worktree remove --force $Path 2>&1 | Out-Null
    git worktree prune 2>&1 | Out-Null
    if (Test-Path $Path) { Remove-Item -Recurse -Force $Path 2>&1 | Out-Null }
    $ErrorActionPreference = $prev
}

function Install-LinuxDeps([string]$AppDir) {
    $py = $null
    foreach ($name in @("py", "python", "python3")) {
        if (Get-Command $name -ErrorAction SilentlyContinue) { $py = $name; break }
    }
    if (-not $py) {
        Write-Host "Python is not on PATH. Azure will try to install packages itself (slower)." -ForegroundColor Yellow
        return $false
    }
    $dest = Join-Path $AppDir "deps"
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Write-Host "Downloading Linux packages (Azure python has no pip)..." -ForegroundColor Cyan
    $pipArgs = @(
        "-m", "pip", "install", "--target", $dest,
        "--platform", "manylinux2014_x86_64",
        "--python-version", "3.11",
        "--implementation", "cp",
        "--abi", "cp311",
        "--only-binary=:all:",
        "-r", (Join-Path $AppDir "requirements.txt")
    )
    if ($py -eq "py") { & py -3 @pipArgs } else { & $py @pipArgs }
    $ok = ($LASTEXITCODE -eq 0) -and (Test-Path (Join-Path $dest "gunicorn"))
    if (-not $ok) {
        Write-Host "Could not vendor Linux packages. Azure will build them on deploy (can take several minutes)." -ForegroundColor Yellow
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    }
    return $ok
}

Write-Host "Using parked FastAPI branch (does not change main / the live site)." -ForegroundColor Cyan
git fetch origin cursor/fastapi-rebuild-parked-0a24
if ($LASTEXITCODE -ne 0) { throw "git fetch failed." }

$work = Join-Path $env:TEMP "achim-fastapi-preview-src"
Clear-PreviewWorktree $work
git worktree add --detach $work origin/cursor/fastapi-rebuild-parked-0a24
if ($LASTEXITCODE -ne 0) { throw "Could not check out the parked FastAPI tree." }

$acct = Get-AzText -AzArgs @("account", "show", "--query", "name", "-o", "tsv")
if ($acct.Code -ne 0 -or -not $acct.Text) {
    throw "az is not logged into a subscription. Run: az login"
}
Write-Host "Azure subscription: $($acct.Text)" -ForegroundColor DarkGray

$listed = Get-AzText -AzArgs @("webapp", "list", "--query", "[].{name:name,resourceGroup:resourceGroup,plan:appServicePlanId}", "-o", "json")
if ($listed.Code -ne 0 -or -not $listed.Text) {
    throw "Could not list Web Apps. Run az login and pick the subscription that has achim-sales-reports."
}
$apps = $listed.Text | ConvertFrom-Json
$live = @($apps | Where-Object { $_.name -eq $LiveName }) | Select-Object -First 1
if (-not $live) {
    $names = @($apps | ForEach-Object { "$($_.name)  ($($_.resourceGroup))" }) -join "`n"
    throw "No Web App named $LiveName in this subscription. Apps I can see:`n$names`nRun: az account list -o table   then   az account set --subscription `"<name>`""
}

if (-not $ResourceGroup) { $ResourceGroup = $live.resourceGroup }
$planName = $Plan
if (-not $planName -and $live.plan) { $planName = $live.plan.Split("/")[-1] }

function Name-FromId([string]$Id) {
    if (-not $Id) { return "" }
    $leaf = $Id.Trim().Split("/")[-1]
    if ($leaf -match "^(ERROR|WARNING|Could not)") { return "" }
    return $leaf
}

if (-not $planName) {
    $shown = Get-AzText -AzArgs @("webapp", "show", "--name", $LiveName, "--resource-group", $ResourceGroup, "-o", "json")
    if ($shown.Code -eq 0 -and $shown.Text.StartsWith("{")) {
        $site = $shown.Text | ConvertFrom-Json
        $planName = Name-FromId ([string]$site.appServicePlanId)
        if (-not $planName) { $planName = Name-FromId ([string]$site.serverFarmId) }
    }
}
if (-not $planName) {
    $farmId = Get-AzText -AzArgs @(
        "resource", "show", "--resource-group", $ResourceGroup,
        "--resource-type", "Microsoft.Web/sites", "--name", $LiveName,
        "--query", "properties.serverFarmId", "-o", "tsv"
    )
    $planName = Name-FromId $farmId.Text
}
if (-not $planName) {
    $farms = Get-AzText -AzArgs @("resource", "list", "--resource-type", "Microsoft.Web/serverfarms", "-o", "json")
    if ($farms.Code -eq 0 -and $farms.Text.StartsWith("[")) {
        $all = @($farms.Text | ConvertFrom-Json)
        $inGroup = @($all | Where-Object { $_.resourceGroup -eq $ResourceGroup })
        if ($inGroup.Count -eq 1) { $planName = $inGroup[0].name }
        elseif ($all.Count -eq 1) { $planName = $all[0].name }
        else {
            $lines = @($all | ForEach-Object { "$($_.name)  ($($_.resourceGroup))" }) -join "`n"
            throw "Found $LiveName in $ResourceGroup but not its plan. Plans I can see:`n$lines`nRe-run: .\preview-site.ps1 -Plan `"PlanName`""
        }
    }
}
if (-not $planName) {
    throw "Found $LiveName in $ResourceGroup but Azure did not return a plan name. In the portal open achim-sales-reports -> App Service plan, then run: .\preview-site.ps1 -Plan `"that name`""
}

Write-Host "Live app $LiveName is in $ResourceGroup on plan $planName." -ForegroundColor DarkGray

try {
    $previewListed = Get-AzText -AzArgs @("webapp", "list", "--resource-group", $ResourceGroup, "--query", "[].name", "-o", "tsv")
    $exists = @($previewListed.Text -split "\r?\n" | Where-Object { $_ }) -contains $Name
    if (-not $exists) {
        Write-Host "Creating $Name on plan $planName..." -ForegroundColor Cyan
        $created = Get-AzText -AzArgs @("webapp", "create", "--name", $Name, "--resource-group", $ResourceGroup, "--plan", $planName, "--runtime", "PYTHON:3.11")
        if ($created.Code -ne 0) { throw "az webapp create failed.`n$($created.Text)" }
    } else {
        Write-Host "Web app $Name already exists. Deploying onto it." -ForegroundColor DarkGray
    }

    $startup = Join-Path $work "app\startup.sh"
    $startupText = [System.IO.File]::ReadAllText($startup)
    $startupText = $startupText.Replace(
        "if [ -x `"`${ROOT}/.venv/bin/python`" ]; then`r`n  PY=`"`${ROOT}/.venv/bin/python`"`r`nelse`r`n  PY=`"`$(command -v python3)`"`r`nfi",
        "if [ -x `"`${ROOT}/.venv/bin/python`" ]; then`r`n  PY=`"`${ROOT}/.venv/bin/python`"`r`nelif [ -x `"`${ROOT}/antenv/bin/python`" ]; then`r`n  PY=`"`${ROOT}/antenv/bin/python`"`r`nelse`r`n  PY=`"`$(command -v python3)`"`r`nfi"
    )
    if ($startupText -notmatch "antenv/bin/python") {
        $startupText = $startupText.Replace(
            "if [ -x `"`${ROOT}/.venv/bin/python`" ]; then`n  PY=`"`${ROOT}/.venv/bin/python`"`nelse`n  PY=`"`$(command -v python3)`"`nfi",
            "if [ -x `"`${ROOT}/.venv/bin/python`" ]; then`n  PY=`"`${ROOT}/.venv/bin/python`"`nelif [ -x `"`${ROOT}/antenv/bin/python`" ]; then`n  PY=`"`${ROOT}/antenv/bin/python`"`nelse`n  PY=`"`$(command -v python3)`"`nfi"
        )
    }
    [System.IO.File]::WriteAllText($startup, $startupText)

    $vendored = Install-LinuxDeps (Join-Path $work "app")
    $buildFlag = "false"
    if (-not $vendored) { $buildFlag = "true" }

    $copy = @(
        "REPORTING_API_KEY", "REPORTING_API_BASE_URL",
        "EMAIL_FROM", "EMAIL_FROM_ADDRESS", "SP_SITE_URL",
        "FLASK_SECRET", "FLASK_SECRET_KEY"
    )
    $pairs = @(
        "APP_ENV=preview",
        "APP_DB_PATH=/tmp/homedata/home.sqlite",
        "SCM_DO_BUILD_DURING_DEPLOYMENT=$buildFlag",
        "ENABLE_ORYX_BUILD=$buildFlag"
    )
    foreach ($key in $copy) {
        $got = Get-AzText -AzArgs @(
            "webapp", "config", "appsettings", "list",
            "--name", $LiveName, "--resource-group", $ResourceGroup,
            "--query", "[?name=='$key'].value | [0]", "-o", "tsv"
        )
        if ($got.Text) { $pairs += "$key=$($got.Text)" }
    }

    $setArgs = @("webapp", "config", "appsettings", "set", "--name", $Name, "--resource-group", $ResourceGroup, "--settings") + $pairs
    $set = Get-AzText -AzArgs $setArgs
    if ($set.Code -ne 0) { throw "Could not set preview App Settings.`n$($set.Text)" }
    Get-AzText -AzArgs @(
        "webapp", "config", "appsettings", "delete",
        "--name", $Name, "--resource-group", $ResourceGroup,
        "--setting-names", "GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET"
    ) | Out-Null

    $boot = Get-AzText -AzArgs @("webapp", "config", "set", "--name", $Name, "--resource-group", $ResourceGroup, "--startup-file", "bash /home/site/wwwroot/startup.sh")
    if ($boot.Code -ne 0) { throw "Could not set Startup Command.`n$($boot.Text)" }

    $deployScript = Join-Path $work "app\deploy.ps1"
    $deployText = [System.IO.File]::ReadAllText($deployScript)
    $oldDeploy = 'az webapp deploy --name $Name --resource-group AchimReportsApp --type zip --src-path $zipPath'
    $newDeploy = @'
Write-Host "Stopping the preview app so Kudu can take the zip..."
az webapp stop --name $Name --resource-group AchimReportsApp
Start-Sleep -Seconds 15
$deployed = $false
foreach ($attempt in 1..3) {
    Write-Host "Deploy attempt $attempt of 3..."
    az webapp deployment source config-zip --name $Name --resource-group AchimReportsApp --src $zipPath --timeout 1800
    if ($LASTEXITCODE -eq 0) { $deployed = $true; break }
    Write-Host "Kudu returned an error. Waiting, then trying again." -ForegroundColor Yellow
    az webapp restart --name $Name --resource-group AchimReportsApp
    Start-Sleep -Seconds 30
}
az webapp start --name $Name --resource-group AchimReportsApp | Out-Null
if (-not $deployed) { throw "Zip deploy failed after 3 tries. The preview app was left started." }
'@
    if (-not $deployText.Contains($oldDeploy)) {
        throw "Parked deploy.ps1 changed. Cannot swap in the Kudu retry."
    }
    [System.IO.File]::WriteAllText($deployScript, $deployText.Replace($oldDeploy, $newDeploy.TrimEnd()))

    Write-Host "Zip-deploying parked FastAPI (not the live site)..." -ForegroundColor Cyan
    & $deployScript -Name $Name
    if ($LASTEXITCODE -ne 0) { throw "Preview deploy failed." }
} finally {
    Clear-PreviewWorktree $work
}

$hostGot = Get-AzText -AzArgs @("webapp", "show", "--name", $Name, "--resource-group", $ResourceGroup, "--query", "defaultHostName", "-o", "tsv")
Write-Host ""
Write-Host "Preview: https://$($hostGot.Text)/login" -ForegroundColor Green
Write-Host "Achim User Login is Preview Admin. Entra stays on the live site."
Write-Host "reports.achimonline.com is still Flask."
