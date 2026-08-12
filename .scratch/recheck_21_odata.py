"""Re-check the 21 TEST-only SOs against OData HeadersV3 vs SalesTableCDR / SalesLineCDR."""
from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()
from config.settings import get_client_id, get_client_secret, get_d365_env_url, get_tenant_id
from core.auth import get_d365_token

SOS = [
    "ORD00870951", "ORD00873658", "ORD00885462", "ORD00885496", "ORD00885427",
    "ORD00886819", "ORD00886159", "ORD00868376", "ORD00868340", "ORD00886371",
    "ORD00886157", "ORD00886152", "ORD00886372", "ORD00868307", "ORD00865884",
    "ORD00848192", "ORD00863771", "ORD00865989", "ORD00873667", "ORD00886153",
    "ORD00886154",
]

env = get_d365_env_url().rstrip("/")
if not env.lower().endswith("/data"):
    env += "/data"
token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), get_d365_env_url())
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
}

def get(entity, filt, select=None):
    q = {"$filter": filt, "cross-company": "true"}
    if select:
        q["$select"] = select
    r = requests.get(f"{env}/{entity}", params=q, headers=headers, timeout=120)
    if r.status_code != 200:
        return r.status_code, []
    return 200, r.json().get("value") or []

print(f"{'SO':<14} {'HeadersV3':>9} {'TableCDR':>9} {'LineCDR':>8} hdr_created  line_min")
print("-" * 80)
for so in SOS:
    hs, hv = get(
        "SalesOrderHeadersV3",
        f"SalesOrderNumber eq '{so}'",
        "SalesOrderNumber,OrderCreationDateTime,dataAreaId",
    )
    ts, tv = get(
        "SalesTableCDREntities",
        f"SalesId eq '{so}'",
        "SalesId,SysCreatedDateTime,CreatedOn,SysDataAreaId,SalesStatus",
    )
    ls, lv = get(
        "SalesLineCDREntities",
        f"SalesId eq '{so}'",
        "SalesId,LineNum,SysCreatedDateTime,CreatedOn",
    )
    hdr_n = len(hv)
    tab_n = len(tv)
    line_n = len(lv)
    hdr_c = (hv[0].get("OrderCreationDateTime") or "")[:10] if hv else ""
    tab_c = ((tv[0].get("SysCreatedDateTime") or tv[0].get("CreatedOn") or "")[:10] if tv else "")
    line_days = sorted({
        (x.get("SysCreatedDateTime") or x.get("CreatedOn") or "")[:10]
        for x in lv if (x.get("SysCreatedDateTime") or x.get("CreatedOn"))
    })
    line_min = line_days[0] if line_days else ""
    print(f"{so:<14} {hdr_n:>9} {tab_n:>9} {line_n:>8} {hdr_c or tab_c or '-':<12} {line_min or '-'}")

print("\nNote: LIVE ordered uses SalesOrderHeadersV3 by OrderCreationDateTime;")
print("      if HeadersV3=0, LIVE never sees the SO regardless of CDR lines.")
