# Sales Reports Web App

Mobile-friendly web app for running D365 F&O sales reports. Authenticated via Microsoft Entra ID (Azure AD).

## Quick Start (Local Development)

### Prerequisites

- Python 3.11+
- The existing scripts `.env` file configured with D365 credentials
- Your Azure AD app registration must have a **Web** redirect URI added:
  `http://localhost:5000/auth/callback`

### Setup

```bash
cd scripts/webapp
pip install -r requirements.txt
```

### Add yourself to the user map

Edit `webapp/user_map.json` to add your Microsoft email:

```json
{
    "users": {
        "your.email@achimimporting.com": {
            "role": "admin"
        }
    }
}
```

For salesmen, include their salesman key:

```json
{
    "users": {
        "salesman@achimimporting.com": {
            "role": "salesman",
            "salesman_key": "mkolko"
        }
    }
}
```

The `salesman_key` must match a key in `config/salesman_map.py` (the normalized sales group, e.g., `mkolko`, `hkaufman`, `blevin`).

### Run

```bash
cd scripts
python -m webapp.app
```

Open http://localhost:5000 in your browser. Sign in with your Microsoft account.

## Azure AD App Registration Setup

The web app reuses the same app registration as the existing scripts (`GRAPH_CLIENT_ID`). You need to add a redirect URI for the web login flow:

1. Go to [Azure Portal](https://portal.azure.com) > Azure Active Directory > App registrations
2. Find your app (the one matching `GRAPH_CLIENT_ID`)
3. Go to **Authentication** > **Platform configurations**
4. Click **Add a platform** > **Web**
5. Add redirect URI: `http://localhost:5000/auth/callback` (for local dev)
6. For production, also add: `https://your-app.azurewebsites.net/auth/callback`
7. Under **Implicit grant and hybrid flows**, check **ID tokens**
8. Save

## Architecture

```
webapp/
  app.py          — Flask routes and request handling
  auth.py         — Microsoft login (MSAL authorization code flow)
  config.py       — Configuration (reads from parent scripts/.env)
  user_map.py     — User-to-role mapping + report access control
  user_map.json   — User email -> role/salesman_key mapping data
  report_api.py   — Bridge to existing report runners
  templates/      — HTML templates (Jinja2)
  static/         — CSS and JavaScript
```

The web app imports the existing report runners directly. When you change report logic in `scripts/reports/`, the web app picks up changes automatically on next run.

## User Roles

- **Admin**: Can see and run all 6 reports. Can select any salesman or customer.
- **Salesman**: Can only see reports that support salesman filtering (Ordered, Invoiced, Customer Activity). Their salesman ID is auto-injected. Customer dropdown only shows their customers.

## Deployment (Deferred)

When ready to deploy, recommended options:

1. **Azure App Service** (recommended) — `az webapp up --name achim-reports --runtime PYTHON:3.11`
2. **GitHub + auto-deploy** — push to repo, Azure deploys automatically
3. **Manual ZIP deploy** — upload via Azure Portal

Set these environment variables in App Service (same as `.env`):
- `D365_ENV_URL`
- `GRAPH_TENANT_ID`
- `GRAPH_CLIENT_ID`
- `GRAPH_CLIENT_SECRET`
- `D365_COMPANY_ID`
- `FLASK_SECRET_KEY` (generate a random string for production)
