# Publish universal_runbook.py to Azure Automation
# Usage: .\deploy-runbook.ps1
#
# Requires: Azure CLI (az) logged in, with the automation extension.
# Uses AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_AUTOMATION_ACCOUNT
# from .env (or defaults).

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$runbookFile = Join-Path $scriptDir "runbooks\universal_runbook.py"
if (-not (Test-Path $runbookFile)) {
    Write-Host "ERROR: $runbookFile not found" -ForegroundColor Red
    exit 1
}

# Load .env if present
$envFile = Join-Path $scriptDir ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim().Trim('"').Trim("'")
            if (-not [System.Environment]::GetEnvironmentVariable($key)) {
                [System.Environment]::SetEnvironmentVariable($key, $val)
            }
        }
    }
}

$SUB_ID   = $env:AZURE_SUBSCRIPTION_ID
$RG       = if ($env:AZURE_RESOURCE_GROUP)      { $env:AZURE_RESOURCE_GROUP }      else { "Daily_Invoiced_Report" }
$ACCOUNT  = if ($env:AZURE_AUTOMATION_ACCOUNT)   { $env:AZURE_AUTOMATION_ACCOUNT }   else { "DailyInvoicedReport" }
$RUNBOOK  = if ($env:AZURE_RUNBOOK_NAME)         { $env:AZURE_RUNBOOK_NAME }         else { "universal_runbook" }

if (-not $SUB_ID) {
    Write-Host "ERROR: AZURE_SUBSCRIPTION_ID not set (check .env or environment)" -ForegroundColor Red
    exit 1
}

Write-Host "Publishing runbook to Azure Automation..." -ForegroundColor Cyan
Write-Host "  Subscription : $SUB_ID"
Write-Host "  Resource Group: $RG"
Write-Host "  Account       : $ACCOUNT"
Write-Host "  Runbook       : $RUNBOOK"
Write-Host "  Source        : $runbookFile"
Write-Host ""

# Ensure the automation extension is installed
$ErrorActionPreference = "Continue"
az extension add --name automation --yes 2>&1 | Out-Null
$ErrorActionPreference = "Stop"

# Set subscription
az account set --subscription $SUB_ID

# Step 1: Replace draft content
Write-Host "Uploading draft content..." -ForegroundColor Yellow
$contentArg = "@$runbookFile"
az automation runbook replace-content --automation-account-name $ACCOUNT --resource-group $RG --name $RUNBOOK --content $contentArg --subscription $SUB_ID --no-wait
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to upload runbook content" -ForegroundColor Red
    exit 1
}
Write-Host "  Draft uploaded." -ForegroundColor DarkGray

# Step 2: Publish
Write-Host "Publishing..." -ForegroundColor Yellow
az automation runbook publish --automation-account-name $ACCOUNT --resource-group $RG --name $RUNBOOK --subscription $SUB_ID --no-wait
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to publish runbook" -ForegroundColor Red
    exit 1
}

Write-Host "`nRunbook '$RUNBOOK' published successfully." -ForegroundColor Green
