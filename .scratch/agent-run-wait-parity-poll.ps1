$ErrorActionPreference = "Continue"
Set-Location "D:\Projects\Achim\AchimSales"
$deadline = (Get-Date).AddSeconds(1800)
while ((Get-Date) -lt $deadline) {
  $tail = @(Get-Content ".scratch\parity-postfix.log" -Tail 8 -ErrorAction SilentlyContinue)
  Write-Output ("--- {0} ---" -f (Get-Date -Format HH:mm:ss))
  $tail | ForEach-Object { Write-Output $_ }
  $full = Get-Content ".scratch\parity-postfix.log" -Raw -ErrorAction SilentlyContinue
  if ($full -match "=== EXIT") { break }
  Start-Sleep -Seconds 90
}
Write-Output "POLL_SLICE_DONE"
