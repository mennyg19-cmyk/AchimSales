"""Fill header dates for SOs missing from SalesOrderHeadersV3 via SalesTableCDREntities."""
from __future__ import annotations

from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()
from config.settings import get_client_id, get_client_secret, get_d365_env_url, get_tenant_id
from core.auth import get_d365_token

MISSING = [
    "ORD00848192", "ORD00868307", "ORD00868340", "ORD00868376", "ORD00870951",
    "ORD00873658", "ORD00873667", "ORD00885427", "ORD00885462", "ORD00885496",
    "ORD00886152", "ORD00886153", "ORD00886154", "ORD00886157", "ORD00886159",
    "ORD00886371", "ORD00886372", "ORD00886819",
]

env = get_d365_env_url().rstrip("/")
if not env.lower().endswith("/data"):
    env = env + "/data"
token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), get_d365_env_url())
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
}

filt = " or ".join(f"SalesId eq '{s}'" for s in MISSING)
r = requests.get(
    f"{env}/SalesTableCDREntities",
    params={
        "$filter": filt,
        "$select": "SalesId,SysCreatedDateTime,CreatedOn,SysDataAreaId,SalesStatus,CustAccount",
        "cross-company": "true",
    },
    headers=headers,
    timeout=120,
)
print("status", r.status_code)
if r.status_code != 200:
    print(r.text[:600])
else:
    rows = r.json().get("value") or []
    print("rows", len(rows))
    by = {x["SalesId"]: x for x in rows}
    for s in MISSING:
        x = by.get(s)
        if not x:
            print(s, "MISSING from SalesTableCDR too")
            continue
        created = (x.get("SysCreatedDateTime") or x.get("CreatedOn") or "")[:10]
        print(s, "created=", created, "status=", x.get("SalesStatus"), "co=", x.get("SysDataAreaId"), "cust=", x.get("CustAccount"))
