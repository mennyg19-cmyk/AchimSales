# Deploy the unified container (live app + /v2) to Azure App Service.
#
# Usage:
#   .\deploy.ps1                # build + push + set container + restart
#   .\deploy.ps1 -SkipBuild     # redeploy current ACR image without rebuilding
#   .\deploy.ps1 -BuildOnly     # build and push, but don't touch App Service
#
# Prerequisites (one-time):
#   az login
#   az account set --subscription <your-sub-id>
#   An Azure Container Registry (ACR) in the same subscription. If you don't
#   have one yet, create it once:
#       az acr create --resource-group AchimReportsApp `
#                     --name achimreportsregistry `
#                     --sku Basic --admin-enabled true
#   Then enable App Service to pull from it:
#       az webapp config container set `
#           --name achim-sales-reports --resource-group AchimReportsApp `
#           --container-registry-url https://achimreportsregistry.azurecr.io
#
# The build runs in Azure (`az acr build`), so Docker Desktop is NOT required
# locally. ACR builds the image from the repo root and pushes automatically.

[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"

# --- Config -----------------------------------------------------------------
$APP_NAME       = "achim-sales-reports"
$RG             = "AchimReportsApp"
$ACR_NAME       = "achimreportsregistry"
$IMAGE_NAME     = "achim-sales-reports"
$TIMESTAMP_TAG  = Get-Date -Format "yyyyMMdd-HHmmss"
$LATEST_TAG     = "latest"
$IMAGE_FULL     = "$ACR_NAME.azurecr.io/${IMAGE_NAME}:${TIMESTAMP_TAG}"
$IMAGE_LATEST   = "$ACR_NAME.azurecr.io/${IMAGE_NAME}:${LATEST_TAG}"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$totalTimer = [System.Diagnostics.Stopwatch]::StartNew()

# --- Step 1: Build + push via ACR Build ------------------------------------
if (-not $SkipBuild) {
    Write-Host "Building image in ACR ($ACR_NAME)..." -ForegroundColor Cyan
    $stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

    az acr build `
        --registry $ACR_NAME `
        --resource-group $RG `
        --image "${IMAGE_NAME}:${TIMESTAMP_TAG}" `
        --image "${IMAGE_NAME}:${LATEST_TAG}" `
        --file Dockerfile `
        . | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "az acr build failed (exit $LASTEXITCODE)" }

    $elapsed = [math]::Round($stepTimer.Elapsed.TotalSeconds, 1)
    Write-Host "  Build + push complete (${elapsed}s)" -ForegroundColor DarkGray
    Write-Host "  Tag: $IMAGE_FULL" -ForegroundColor DarkGray
}
else {
    Write-Host "Skipping build (-SkipBuild). Using existing '$LATEST_TAG' tag." -ForegroundColor Yellow
}

if ($BuildOnly) {
    $totalElapsed = [math]::Round($totalTimer.Elapsed.TotalSeconds, 1)
    Write-Host "`nBuild-only done. Total: ${totalElapsed}s" -ForegroundColor Green
    return
}

# --- Step 2: Point App Service at the new tag ------------------------------
Write-Host "`nPointing App Service at '$LATEST_TAG' tag..." -ForegroundColor Cyan
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

az webapp config container set `
    --name $APP_NAME --resource-group $RG `
    --container-image-name $IMAGE_LATEST | Out-Null
if ($LASTEXITCODE -ne 0) { throw "az webapp config container set failed (exit $LASTEXITCODE)" }

$elapsed = [math]::Round($stepTimer.Elapsed.TotalSeconds, 1)
Write-Host "  Container config updated (${elapsed}s)" -ForegroundColor DarkGray

# --- Step 3: Restart so the new image pulls --------------------------------
Write-Host "`nRestarting App Service..." -ForegroundColor Cyan
$stepTimer.Restart()

az webapp restart --name $APP_NAME --resource-group $RG | Out-Null
if ($LASTEXITCODE -ne 0) { throw "az webapp restart failed (exit $LASTEXITCODE)" }

$elapsed = [math]::Round($stepTimer.Elapsed.TotalSeconds, 1)
Write-Host "  Restart triggered (${elapsed}s)" -ForegroundColor DarkGray

# --- Step 4: Wait for readiness --------------------------------------------
Write-Host "`nWaiting for /healthz..." -ForegroundColor Cyan
$stepTimer.Restart()

$hostname = az webapp show --name $APP_NAME --resource-group $RG --query defaultHostName -o tsv
if (-not $hostname) { throw "Could not resolve App Service hostname." }

$healthUrl = "https://${hostname}/v2/healthz"
$deadline  = (Get-Date).AddMinutes(5)
$ready     = $false
while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 5 }
}

$elapsed = [math]::Round($stepTimer.Elapsed.TotalSeconds, 1)
if ($ready) {
    Write-Host "  /v2/healthz responded OK (${elapsed}s)" -ForegroundColor DarkGray
} else {
    Write-Warning "  /v2/healthz did not respond within 5 min. Check App Service logs."
}

$totalElapsed = [math]::Round($totalTimer.Elapsed.TotalSeconds, 1)
Write-Host "`nDone! Total: ${totalElapsed}s" -ForegroundColor Green
Write-Host "  Live: https://${hostname}/" -ForegroundColor DarkGray
Write-Host "  v2:   https://${hostname}/v2/" -ForegroundColor DarkGray
