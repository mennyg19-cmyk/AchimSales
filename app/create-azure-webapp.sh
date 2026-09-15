#!/usr/bin/env bash
# Create a NEW Azure Web App for this rebuild. Does not touch the live site.
#
# Required: az login
# Usage: bash create-azure-webapp.sh <new-name>
# Example: bash create-azure-webapp.sh achim-sales-home-preview

set -euo pipefail

NAME="${1:-}"
GROUP="${AZURE_RESOURCE_GROUP:-AchimReportsApp}"
PLAN="${AZURE_APP_SERVICE_PLAN:-mennyg_asp_5084}"
LOCATION="${AZURE_LOCATION:-canadacentral}"

if [ -z "${NAME}" ]; then
  echo "Usage: bash create-azure-webapp.sh <new-webapp-name>" >&2
  exit 1
fi
if [ "${NAME}" = "achim-sales-reports" ]; then
  echo "Refusing to create/replace the live site name." >&2
  exit 1
fi

az webapp create \
  --resource-group "${GROUP}" \
  --plan "${PLAN}" \
  --name "${NAME}" \
  --runtime "PYTHON:3.12" \
  --https-only true

az webapp config set \
  --resource-group "${GROUP}" \
  --name "${NAME}" \
  --startup-file "bash /home/site/wwwroot/startup.sh"

az webapp config appsettings set \
  --resource-group "${GROUP}" \
  --name "${NAME}" \
  --settings \
    APP_ENV=preview \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    WEBSITES_PORT=8000

echo "Created ${NAME}. Next: from the app/ folder run:  ./deploy.ps1 -Name ${NAME}"
echo "Then set SESSION_SECRET in Configuration if you switch APP_ENV to production."
echo "Do not bind reports.achimonline.com until Menny signs off."
