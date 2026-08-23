"""Probe SalesLineCDREntity for SysCreatedDateTime / CreatedOn vs header OrderCreationDateTime."""
import re
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

for entity in ("SalesLineCDREntity", "SalesTableCDREntity"):
    r = requests.get(
        f"{env}/data/{entity}",
        params={"$top": "1", "cross-company": "true"},
        headers=headers,
        timeout=60,
    )
    print(entity, "top1", r.status_code)
    if r.status_code == 200 and r.json().get("value"):
        keys = sorted(r.json()["value"][0].keys())
        interesting = [k for k in keys if re.search(r"sales|order|line|item|creat|date|invent|qty|num", k, re.I)]
        print("  interesting:", interesting)
    else:
        print(r.text[:400])

for field in ("SalesId", "SalesOrderNumber"):
    for sel in (
        f"{field},ItemId,LineNum,SysCreatedDateTime,CreatedOn",
        f"{field},ItemId,LineNumber,SysCreatedDateTime,CreatedOn",
    ):
        r = requests.get(
            f"{env}/data/SalesLineCDREntity",
            params={
                "$filter": f"{field} eq '{so}'",
                "$select": sel,
                "$top": "5",
                "cross-company": "true",
            },
            headers=headers,
            timeout=60,
        )
        print(f"filter {field} select={sel[:40]}…", r.status_code)
        print(r.text[:500])
        if r.status_code == 200:
            break
