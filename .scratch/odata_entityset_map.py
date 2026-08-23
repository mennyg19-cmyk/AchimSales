"""Map EntityType SalesLineCDREntity -> EntitySet name; also confirm HeadersV3 works."""
import re
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
import requests
from config.settings import get_client_id, get_client_secret, get_d365_env_url, get_tenant_id
from core.auth import get_d365_token

# reuse cached metadata if present
meta_path = Path(".scratch/odata_metadata.xml")
env = get_d365_env_url().rstrip("/")
token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), env)
headers = {"Authorization": f"Bearer {token}", "Accept": "application/xml"}

if not meta_path.exists() or meta_path.stat().st_size < 1000:
    print("Downloading metadata…")
    r = requests.get(f"{env}/data/$metadata", headers=headers, timeout=180)
    meta_path.write_text(r.text, encoding="utf-8")
    text = r.text
else:
    print("Using cached metadata")
    text = meta_path.read_text(encoding="utf-8")

for etype in ("SalesLineCDREntity", "SalesTableCDREntity", "SalesOrderLineV3", "SalesOrderHeaderV3"):
    sets = re.findall(rf'<EntitySet Name="([^"]+)" EntityType="[^"]*\.{etype}"', text)
    print(etype, "EntitySets:", sets)

# Working header fetch
headers_json = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
}
so = "ORD00866879"
r = requests.get(
    f"{env}/data/SalesOrderHeadersV3",
    params={
        "$select": "SalesOrderNumber,OrderCreationDateTime,InvoiceCustomerAccountNumber",
        "$filter": f"SalesOrderNumber eq '{so}'",
        "$top": "1",
        "cross-company": "true",
    },
    headers=headers_json,
    timeout=60,
)
print("\nheader OK?", r.status_code, r.text[:400])

# Lines without CreatedDateTime
r = requests.get(
    f"{env}/data/SalesOrderLinesV3",
    params={
        "$select": "SalesOrderNumber,LineNumber,ItemNumber,RequestedShippingDate,ConfirmedShippingDate",
        "$filter": f"SalesOrderNumber eq '{so}'",
        "$top": "10",
        "cross-company": "true",
    },
    headers=headers_json,
    timeout=60,
)
print("lines OK?", r.status_code)
if r.status_code == 200:
    for row in r.json().get("value") or []:
        print(row)
