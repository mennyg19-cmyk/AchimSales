$ErrorActionPreference = "Continue"
$rg = "Daily_Invoiced_Report"
$acct = "DailyInvoicedReport"

Write-Host "=== Amazon Monthly Ordered job schedule params ==="
az automation job-schedule list -g $rg --automation-account-name $acct -o json 2>$null |
  Out-File .scratch/job-schedules.json -Encoding utf8

$raw = Get-Content .scratch/job-schedules.json -Raw
$items = ($raw | ConvertFrom-Json)
foreach ($js in $items) {
  $name = $js.properties.schedule.name
  $rb = $js.properties.runbook.name
  $params = $js.properties.parameters
  if ($name -match "Month|Amazon|Invoiced|Salesman|Customer") {
    Write-Host ("{0} | runbook={1} | report={2} | args={3}" -f $name, $rb, $params.report_name, $params.extra_args)
  }
}
