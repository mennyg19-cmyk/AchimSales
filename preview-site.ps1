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
    $text = az @AzArgs | Out-String
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    return @{ Code = $code; Text = $text.Trim() }
}

function Clear-PreviewWorktree([string]$Path) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    git worktree remove --force $Path 2>&1 | Out-Null
    git worktree prune 2>&1 | Out-Null
    $ErrorActionPreference = $prev
    if (Test-Path $Path) { Remove-Item -Recurse -Force $Path }
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
if (-not $planName) {
    $plans = Get-AzText -AzArgs @("appservice", "plan", "list", "--resource-group", $ResourceGroup, "--query", "[].name", "-o", "tsv")
    $planNames = @($plans.Text -split "\r?\n" | Where-Object { $_ })
    if ($planNames.Count -eq 1) { $planName = $planNames[0] }
}
if (-not $planName) {
    throw "Found $LiveName in $ResourceGroup but not its plan. Re-run with -Plan `"YourPlanName`"."
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

    $copy = @(
        "REPORTING_API_KEY", "REPORTING_API_BASE_URL",
        "GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET",
        "EMAIL_FROM", "EMAIL_FROM_ADDRESS", "SP_SITE_URL",
        "FLASK_SECRET", "FLASK_SECRET_KEY"
    )
    $pairs = @("APP_ENV=preview", "APP_DB_PATH=/tmp/homedata/home.sqlite")
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

    $boot = Get-AzText -AzArgs @("webapp", "config", "set", "--name", $Name, "--resource-group", $ResourceGroup, "--startup-file", "bash /home/site/wwwroot/startup.sh")
    if ($boot.Code -ne 0) { throw "Could not set Startup Command.`n$($boot.Text)" }

    Write-Host "Zip-deploying parked FastAPI (not the live site)..." -ForegroundColor Cyan
    & (Join-Path $work "app\deploy.ps1") -Name $Name
    if ($LASTEXITCODE -ne 0) { throw "Preview deploy failed." }
} finally {
    Clear-PreviewWorktree $work
}

$hostGot = Get-AzText -AzArgs @("webapp", "show", "--name", $Name, "--resource-group", $ResourceGroup, "--query", "defaultHostName", "-o", "tsv")
Write-Host ""
Write-Host "Preview: https://$($hostGot.Text)/login" -ForegroundColor Green
Write-Host "Achim User Login is Preview Admin (Entra stays on the live host)."
Write-Host "reports.achimonline.com is still Flask."
