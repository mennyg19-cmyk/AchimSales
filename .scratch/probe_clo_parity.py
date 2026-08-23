"""Compare CLO recent-orders for the CA leftover accounts (live vs /test)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
env = dotenv_values(ROOT / ".scratch" / "parity-cookies.env")
for k, v in env.items():
    if v:
        os.environ[k] = v

BASE = os.environ.get("PARITY_BASE_URL", "https://reports.achimonline.com").rstrip("/")
LIVE = os.environ["PARITY_LIVE_COOKIE"].strip()
TEST = os.environ["PARITY_TEST_COOKIE"].strip()

# CA leftovers after noise filter
ACCOUNTS = ["00011016", "3316837", "2449"]
# Also a few high-volume that differed only by same-day SO (sanity)
EXTRA = ["9022", "1412", "7025"]


def live_recent(account: str) -> dict:
    r = requests.get(
        f"{BASE}/api/report/customer-last-order/{account}/recent-invoiced",
        headers={"Cookie": f"session={LIVE}"},
        timeout=120,
        allow_redirects=False,
    )
    return {"status": r.status_code, "body": _json_or_text(r)}


def test_recent(account: str) -> dict:
    r = requests.get(
        f"{BASE}/test/api/report/customer-last-order/{account}/recent-invoiced",
        headers={"Cookie": f"v3_session={TEST}"},
        timeout=120,
        allow_redirects=False,
    )
    return {"status": r.status_code, "body": _json_or_text(r)}


def _json_or_text(r: requests.Response):
    try:
        return r.json()
    except Exception:
        return {"_text": r.text[:500], "_loc": r.headers.get("Location")}


def summarize(side: str, payload: dict) -> None:
    print(f"  {side}: HTTP {payload['status']}")
    body = payload["body"]
    if not isinstance(body, dict):
        print(f"    raw={body!r}")
        return
    if "_text" in body:
        print(f"    redirect/text={body}")
        return
    orders = body.get("orders") or []
    print(f"    orders={len(orders)}")
    for o in orders[:5]:
        print(
            f"      {o.get('order_number')} date={o.get('order_date')} "
            f"po={o.get('customer_req')!r} status={o.get('status')!r}"
        )


def main() -> None:
    for acct in ACCOUNTS + EXTRA:
        print(f"=== {acct} ===")
        try:
            summarize("live", live_recent(acct))
        except Exception as e:
            print(f"  live ERR {e}")
        try:
            summarize("test", test_recent(acct))
        except Exception as e:
            print(f"  test ERR {e}")
        print()


if __name__ == "__main__":
    main()
