$ErrorActionPreference = "Continue"
$rg = "Daily_Invoiced_Report"
$acct = "DailyInvoicedReport"
$sub = "2dd40e64-12e2-4dd4-a5be-13515a2d382f"
$job = "d053cda2-183d-43ef-81f9-5ae1b0efbbd1"

# Pull streams; print last 25 summaries
az rest --method get --url "https://management.azure.com/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.Automation/automationAccounts/$acct/jobs/$job/streams?api-version=2023-11-01" -o json 2>$null |
  Out-File .scratch/catchup-streams-full.json -Encoding utf8

$j = Get-Content .scratch/catchup-streams-full.json -Raw | ConvertFrom-Json
Write-Host "Stream count:" $j.value.Count
Write-Host "`n=== LAST 25 ==="
$j.value | Select-Object -Last 25 | ForEach-Object { Write-Host $_.properties.summary }

$info = az automation job show -g $rg --automation-account-name $acct --name $job -o json 2>$null | ConvertFrom-Json
Write-Host "`nFinal status:" $info.status "exception:" $info.exception
