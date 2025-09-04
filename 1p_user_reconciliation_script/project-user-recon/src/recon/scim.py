# src/recon/scim.py
import os, requests
from typing import Dict
from urllib.parse import quote
from .util import DEFAULT_TIMEOUT, RETRY_STATUS, backoff_sleep

BASE = (os.getenv("OP_SCIM_BASE_URL") or "").rstrip("/")
TOKEN = (os.getenv("OP_SCIM_BEARER_TOKEN") or "").strip()

def _hdrs(json_scim: bool = False) -> Dict[str, str]:
    if not BASE or not TOKEN:
        raise RuntimeError("Missing OP_SCIM_BASE_URL or OP_SCIM_BEARER_TOKEN")
    h = {"Authorization": f"Bearer {TOKEN}"}
    if json_scim:
        h["Content-Type"] = "application/scim+json"
    return h

def _req(method: str, url: str, **kw) -> requests.Response:
    for i in range(6):
        r = requests.request(method, url, headers=_hdrs(kw.pop("json_scim", False)),
                             timeout=DEFAULT_TIMEOUT, **kw)
        if r.status_code in RETRY_STATUS:
            backoff_sleep(i, r.headers.get("Retry-After"))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r

def scim_self_check() -> None:
    # Ensure correct endpoint; will raise for non-200.
    _req("GET", f"{BASE}/ServiceProviderConfig")

def scim_lookup(email: str) -> dict:
    # DO NOT pre-encode; requests will encode '+' as %2B inside the param value.
    r = _req("GET", f"{BASE}/Users", params={"filter": f'userName eq "{email}"'})
    data = r.json() or {}
    res = (data.get("Resources") or [])
    if res:
        return {"status_code": 200, "error": None, "email": email, "found": True, "user_id": res[0].get("id")}
    return {"status_code": 200, "error": None, "email": email, "found": False, "user_id": None}

def deactivate_user_scim(email: str, dry_run: bool = True) -> dict:
    # Lookup WITHOUT pre-encoding to avoid %252B
    r = _req("GET", f"{BASE}/Users", params={"filter": f'userName eq "{email}"'})
    res = (r.json() or {}).get("Resources") or []
    if not res:
        return {"status_code": 404, "error": "SCIM user not found", "email": email, "user_id": None, "action": "lookup", "body": None}

    scim_id = res[0].get("id")
    if dry_run:
        return {"status_code": 200, "error": None, "email": email, "user_id": scim_id, "action": "dry_run", "body": None}

    # PATCH active=false using object-value form (this worked in your manual test)
    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [{"op": "replace", "value": {"active": False}}],
    }
    pr = _req("PATCH", f"{BASE}/Users/{scim_id}", json=payload, json_scim=True)
    return {
        "status_code": pr.status_code,
        "error": None if pr.status_code < 400 else pr.text,
        "email": email,
        "user_id": scim_id,
        "action": "deactivate",
        "body": pr.text,
    }

