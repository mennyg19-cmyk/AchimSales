#!/usr/bin/env bash
# Azure App Service Startup Command:
#   bash /home/site/wwwroot/startup.sh
#
# This repo's website is FastAPI under app/. The old Flask tree
# (v3/, webapp/, rebuild/) is gone. Azure already runs this file, so
# merging this branch to main is what switches the live Web App.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec bash "${ROOT}/app/startup.sh"
