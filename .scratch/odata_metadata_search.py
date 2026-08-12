"""Find an OData entity that exposes sales-line CreatedDateTime; also validate header-only reconcile path."""
from dotenv import load_dotenv
load_dotenv()
import re
import requests
from config.settings import get_client_id, get_client_secret, get_d365_env_url, get_tenant_id
from core.auth import get_d365_token

env = get_d365_env_url().rstrip("/")
token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), env)
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/xml",
}

print("Fetching $metadata (may be large)…")
r = requests.get(f"{env}/data/$metadata", headers=headers, timeout=180)
print("metadata status", r.status_code, "bytes", len(r.text))
text = r.text
# Find EntityTypes that mention both SalesOrder / SalesLine and CreatedDateTime
# Simpler: all EntityType names containing CreatedDateTime property near Sales
hits = []
for m in re.finditer(r'<EntityType Name="([^"]+)"[^>]*>(.*?)</EntityType>', text, re.S):
    name, body = m.group(1), m.group(2)
    if "CreatedDateTime" in body and re.search(r"Sales|OrderLine|SalesLine", name, re.I):
        props = re.findall(r'<Property Name="([^"]+)"', body)
        dateprops = [p for p in props if re.search(r"date|creat|time", p, re.I)]
        hits.append((name, dateprops[:20]))

print(f"EntityTypes with CreatedDateTime + Sales/OrderLine in name: {len(hits)}")
for name, dates in hits[:40]:
    print(f"  {name}: {dates}")

# Also list any property literally named CreatedDateTime on *Line* entities
line_hits = []
for m in re.finditer(r'<EntityType Name="([^"]*Line[^"]*)"[^>]*>(.*?)</EntityType>', text, re.S):
    name, body = m.group(1), m.group(2)
    if "CreatedDateTime" in body:
        line_hits.append(name)
print("\n*Line* entities with CreatedDateTime:", line_hits[:50])
