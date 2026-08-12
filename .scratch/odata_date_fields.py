"""Probe which date fields exist on SalesOrderHeaderV3 / SalesOrderLineV3."""
from dotenv import load_dotenv
load_dotenv()
import requests
from config.settings import get_client_id, get_client_secret, get_d365_env_url, get_tenant_id
from core.auth import get_d365_token

env = get_d365_env_url().rstrip("/")
token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), env)
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
}
so = "ORD00866879"

# Header known-good
r = requests.get(
    f"{env}/data/SalesOrderHeadersV3",
    params={
        "$select": "SalesOrderNumber,OrderCreationDateTime,OrderDate,RequestedShippingDate,ConfirmedShippingDate",
        "$filter": f"SalesOrderNumber eq '{so}'",
        "$top": "1",
        "cross-company": "true",
    },
    headers=headers,
    timeout=60,
)
print("header", r.status_code, r.text[:600])

# Try line date candidate fields one by one
candidates = [
    "CreatedDateTime",
    "LineCreationDateTime",
    "SalesOrderLineCreationDateTime",
    "OrderLineCreationDateTime",
    "CreationDate",
    "ReceiptDateRequested",
    "ShippingDateRequested",
    "ConfirmedShippingDate",
    "RequestedShippingDate",
    "DeliveryDate",
    "AccountingDate",
]
base_sel = "SalesOrderNumber,LineNumber,ItemNumber"
for field in candidates:
    r = requests.get(
        f"{env}/data/SalesOrderLinesV3",
        params={
            "$select": f"{base_sel},{field}",
            "$filter": f"SalesOrderNumber eq '{so}'",
            "$top": "1",
            "cross-company": "true",
        },
        headers=headers,
        timeout=60,
    )
    ok = r.status_code == 200
    msg = ""
    if not ok:
        try:
            msg = r.json().get("error", {}).get("innererror", {}).get("message", r.text[:120])
        except Exception:
            msg = r.text[:120]
    else:
        val = (r.json().get("value") or [{}])[0]
        msg = f"sample={val.get(field)!r}"
    print(f"{'OK' if ok else 'NO'} {field}: {msg}")

# Also dump one full line without $select to see keys (may be huge — top 1)
r = requests.get(
    f"{env}/data/SalesOrderLinesV3",
    params={"$filter": f"SalesOrderNumber eq '{so}'", "$top": "1", "cross-company": "true"},
    headers=headers,
    timeout=60,
)
print("\nfull line status", r.status_code)
if r.status_code == 200:
    keys = sorted((r.json().get("value") or [{}])[0].keys())
    dateish = [k for k in keys if "date" in k.lower() or "creat" in k.lower() or "time" in k.lower()]
    print("date-ish keys:", dateish)
    print("all keys count", len(keys))
