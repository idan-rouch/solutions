# src/recon/okta.py
import os, time, requests
from typing import Dict, List, Optional
from urllib.parse import quote
from .util import DEFAULT_TIMEOUT, RETRY_STATUS, backoff_sleep

OKTA_BASE = (os.getenv("OKTA_BASE_URL") or "").rstrip("/")
OKTA_TOKEN = (os.getenv("OKTA_API_TOKEN") or "").strip()

def _hdrs() -> Dict[str, str]:
    if not OKTA_BASE or not OKTA_TOKEN:
        raise RuntimeError("Missing OKTA_BASE_URL or OKTA_API_TOKEN")
    return {
        "Authorization": f"SSWS {OKTA_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def _req(method: str, url: str, **kw) -> requests.Response:
    for i in range(6):
        r = requests.request(method, url, headers=_hdrs(), timeout=DEFAULT_TIMEOUT, **kw)
        if r.status_code in RETRY_STATUS:
            backoff_sleep(i, r.headers.get("Retry-After"))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r  # unreachable

def list_okta_users(mock: bool = False) -> List[Dict]:
    if mock:
        return [{"email":"mock@example.com","status":"ACTIVE","id":"00uMOCK"}]
    url = f"{OKTA_BASE}/api/v1/users"
    out: List[Dict] = []
    params = {"limit": 200}
    while True:
        r = _req("GET", url, params=params)
        arr = r.json() or []
        for u in arr:
            prof = u.get("profile") or {}
            out.append({
                "email": (prof.get("login") or prof.get("email") or "").lower(),
                "status": (u.get("status") or "").upper(),
                "id": u.get("id"),
            })
        nxt = r.links.get("next", {}).get("url")
        if not nxt: break
        url, params = nxt, None
    return out

def get_okta_uid_by_login(email: str) -> Optional[str]:
    enc = quote(email, safe="@._-")  # '+' -> %2B
    # exact search
    r = _req("GET", f"{OKTA_BASE}/api/v1/users", params={"search": f'profile.login eq "{enc}"'})
    arr = r.json() or []
    if arr: return arr[0].get("id")
    # fuzzy fallback
    r = _req("GET", f"{OKTA_BASE}/api/v1/users", params={"q": email})
    for u in r.json() or []:
        if (u.get("profile", {}).get("login") or "").lower() == email.lower():
            return u.get("id")
    return None

def add_user_to_group(group_id: str, user_id: str, mock: bool = False) -> None:
    if mock: return
    _req("PUT", f"{OKTA_BASE}/api/v1/groups/{group_id}/users/{user_id}")

def remove_user_from_group(group_id: str, user_id: str, mock: bool = False) -> None:
    if mock: return
    _req("DELETE", f"{OKTA_BASE}/api/v1/groups/{group_id}/users/{user_id}")

def trigger_scim_reprovision(group_id: str, email: str, wait_seconds: int = 3, mock: bool = False) -> Dict:
    uid = get_okta_uid_by_login(email)
    if not uid:
        return {"email": email, "group_id": group_id, "ok": False, "error": "Okta UID not found"}

    try:
        remove_user_from_group(group_id, uid, mock=mock)
    except requests.HTTPError as e:
        if not (e.response is not None and e.response.status_code == 404):
            return {"email": email, "group_id": group_id, "ok": False, "error": f"remove failed: {e}"}
    if not mock and wait_seconds > 0:
        time.sleep(wait_seconds)
    try:
        add_user_to_group(group_id, uid, mock=mock)
    except requests.HTTPError as e:
        return {"email": email, "group_id": group_id, "ok": False, "error": f"add failed: {e}"}
    return {"email": email, "group_id": group_id, "ok": True, "okta_uid": uid}
