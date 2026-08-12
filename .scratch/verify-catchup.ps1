$ErrorActionPreference = "Continue"
$rg = "Daily_Invoiced_Report"
$acct = "DailyInvoicedReport"
$sub = "2dd40e64-12e2-4dd4-a5be-13515a2d382f"
$job = "d053cda2-183d-43ef-81f9-5ae1b0efbbd1"

az rest --method get --url "https://management.azure.com/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.Automation/automationAccounts/$acct/jobs/$job/streams?api-version=2023-11-01" -o json 2>$null |
  Out-File .scratch/catchup-streams.json -Encoding utf8

$j = Get-Content .scratch/catchup-streams.json -Raw | ConvertFrom-Json
Write-Host "=== Key catch-up job lines ==="
foreach ($s in $j.value) {
  $t = [string]$s.properties.summary
  if ($t -match "SUCCESS|FAILED|SKIP|force|period|Uploaded|error|Exception|Last Month|rows|===|exit") {
    Write-Host $t
  }
}
