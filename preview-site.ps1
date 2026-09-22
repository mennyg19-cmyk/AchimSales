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
    [string]$ResourceGroup = "AchimReportsApp",
    [string]$LiveName = "achim-sales-reports"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ($Name.ToLowerInvariant() -eq $LiveName.ToLowerInvariant()) {
    throw "Refusing to deploy FastAPI onto $LiveName. That is the live Flask site."
}

$az = Get-Command az -ErrorAction SilentlyContinue
if (-not $az) { throw "Azure CLI (az) is not on PATH. Install it, run az login, then this script again." }

Write-Host "Using parked FastAPI branch (does not change main / the live site)." -ForegroundColor Cyan
git fetch origin cursor/fastapi-rebuild-parked-0a24
if ($LASTEXITCODE -ne 0) { throw "git fetch failed." }

$work = Join-Path $env:TEMP "achim-fastapi-preview-src"
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
git worktree add --detach $work origin/cursor/fastapi-rebuild-parked-0a24
if ($LASTEXITCODE -ne 0) { throw "Could not check out the parked FastAPI tree." }

try {
    $exists = az webapp show --name $Name --resource-group $ResourceGroup --query name -o tsv 2>$null
    if (-not $exists) {
        $planId = az webapp show --name $LiveName --resource-group $ResourceGroup --query appServicePlanId -o tsv
        if (-not $planId) { throw "Could not read the live app's plan. Check az login and $LiveName." }
        $planName = $planId.Split("/")[-1]
        Write-Host "Creating $Name on plan $planName..." -ForegroundColor Cyan
        az webapp create --name $Name --resource-group $ResourceGroup --plan $planName --runtime "PYTHON:3.11"
        if ($LASTEXITCODE -ne 0) { throw "az webapp create failed." }
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
        $val = az webapp config appsettings list --name $LiveName --resource-group $ResourceGroup --query "[?name=='$key'].value | [0]" -o tsv
        if ($val) { $pairs += "$key=$val" }
    }

    az webapp config appsettings set --name $Name --resource-group $ResourceGroup --settings $pairs
    if ($LASTEXITCODE -ne 0) { throw "Could not set preview App Settings." }

    az webapp config set --name $Name --resource-group $ResourceGroup --startup-file "bash /home/site/wwwroot/startup.sh"
    if ($LASTEXITCODE -ne 0) { throw "Could not set Startup Command." }

    Write-Host "Zip-deploying parked FastAPI (not the live site)..." -ForegroundColor Cyan
    & (Join-Path $work "app\deploy.ps1") -Name $Name
    if ($LASTEXITCODE -ne 0) { throw "Preview deploy failed." }
} finally {
    git worktree remove --force $work 2>$null
}

$hostName = az webapp show --name $Name --resource-group $ResourceGroup --query defaultHostName -o tsv
Write-Host ""
Write-Host "Preview: https://$hostName/login" -ForegroundColor Green
Write-Host "Achim User Login is Preview Admin (Entra stays on the live host)."
Write-Host "reports.achimonline.com is still Flask."
