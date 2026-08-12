$ErrorActionPreference = "Continue"
Write-Host "=== app settings (secrets redacted) ==="
az webapp config appsettings list --name achim-sales-reports --resource-group AchimReportsApp -o json |
  python -c "import json,sys; data=json.load(sys.stdin); keys=('FLASK_SECRET','FLASK_SECRET_KEY','BETA_','AUTH_MODE','APP_ENV','LITESTREAM','PRECIOUS','CACHE','BETA_MOUNT');
[print(f\"{i['name']}={'<set>' if i.get('value') else '<empty>'} len={len(i.get('value') or '')}\") for i in data if any(k in i['name'] for k in ('FLASK_SECRET','FLASK_SECRET_KEY','BETA_','AUTH_MODE','APP_ENV','LITESTREAM','PRECIOUS','CACHE','V3_'))]"
