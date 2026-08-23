$ErrorActionPreference = "Continue"
$rg = "Daily_Invoiced_Report"
$acct = "DailyInvoicedReport"
$job = "d053cda2-183d-43ef-81f9-5ae1b0efbbd1"

for ($i = 1; $i -le 40; $i++) {
  $json = az automation job show -g $rg --automation-account-name $acct --name $job -o json 2>$null
  $info = $json | ConvertFrom-Json
  Write-Host ("[{0}] status={1} start={2} end={3}" -f $i, $info.status, $info.startTime, $info.endTime)
  if ($info.status -in @("Completed", "Failed", "Stopped", "Suspended")) {
    exit 0
  }
  Start-Sleep -Seconds 30
}
Write-Host "Still running after poll window"
exit 2
