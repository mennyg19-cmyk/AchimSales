$ErrorActionPreference = "Stop"
$rg = "Daily_Invoiced_Report"
$acct = "DailyInvoicedReport"
$jobName = [guid]::NewGuid().ToString()
$sub = "2dd40e64-12e2-4dd4-a5be-13515a2d382f"
$bodyPath = Join-Path $PSScriptRoot "start-catchup-body.json"

$json = '{"properties":{"runbook":{"name":"universal_runbook"},"parameters":{"report_name":"invoiced","extra_args":"--period last_month --force"}}}'
[System.IO.File]::WriteAllText($bodyPath, $json)

Write-Host "Starting catch-up job $jobName ..."
az rest --method put `
  --url "https://management.azure.com/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.Automation/automationAccounts/$acct/jobs/$($jobName)?api-version=2023-11-01" `
  --headers "Content-Type=application/json" `
  --body "@$bodyPath" `
  -o json
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host "`nStarted OK: JOB_NAME=$jobName"
