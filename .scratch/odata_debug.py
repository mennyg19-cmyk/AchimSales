"""Debug one OData SalesOrderHeadersV3 call."""
import os
from dotenv import load_dotenv
load_dotenv()
os.environ.setdefault("PYTHONPATH", ".")

from config.settings import get_client_id, get_client_secret, get_company_id, get_d365_env_url, get_tenant_id
from core.auth import get_d365_token
import requests

env = get_d365_env_url().rstrip("/")
token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), env)
company = get_company_id()
print("company", repr(company))
print("env", env)

# pick a known SO from the export
so = "ORD00866879"
url = f"{env}/data/SalesOrderHeadersV3"
params = {
    "$select": "SalesOrderNumber,OrderCreationDateTime,CreatedDateTime",
    "$filter": f"SalesOrderNumber eq '{so}'",
    "$top": "5",
}
headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
if company:
    headers["Company"] = company

r = requests.get(url, params=params, headers=headers, timeout=60)
print("status", r.status_code)
print("content-type", r.headers.get("content-type"))
print("body head", r.text[:800])

# try with cross-company
headers2 = dict(headers)
params2 = dict(params)
params2["cross-company"] = "true"
r2 = requests.get(url, params=params2, headers=headers2, timeout=60)
print("\ncross-company status", r2.status_code)
print("body head", r2.text[:800])

# lines
url3 = f"{env}/data/SalesOrderLinesV3"
params3 = {
    "$select": "SalesOrderNumber,LineNumber,ItemNumber,CreatedDateTime",
    "$filter": f"SalesOrderNumber eq '{so}'",
    "$top": "5",
    "cross-company": "true",
}
r3 = requests.get(url3, params=params3, headers=headers, timeout=60)
print("\nlines status", r3.status_code)
print("body head", r3.text[:1000])
