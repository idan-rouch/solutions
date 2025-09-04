# src/recon/engine.py

from typing import Dict, List, Set, Tuple
from .scim import scim_lookup

ACTIVE_STATUSES_OKTA: Set[str] = {"ACTIVE"}  # Okta user.status
INACTIVE_STATUSES_OKTA: Set[str] = {
    "SUSPENDED",
    "DEPROVISIONED",
    "DEACTIVATED",
    "LOCKED_OUT",
    "STAGED",  # treat as not-active for our purposes
}

def _norm_email(v: str) -> str:
    return (v or "").strip().lower()

def _index_okta(okta_users: List[Dict]) -> Tuple[Dict[str, Dict], Set[str], Set[str]]:
    """
    Returns:
      - by_email: email -> user dict
      - active: set of emails with ACTIVE status
      - inactive: set of emails with non-ACTIVE status (SUSPENDED/DEPROVISIONED/…)
    """
    by_email: Dict[str, Dict] = {}
    active: Set[str] = set()
    inactive: Set[str] = set()

    for u in okta_users or []:
        email = _norm_email(u.get("email"))
        if not email:
            continue
        status = (u.get("status") or "").upper()
        # prefer ACTIVE if duplicates exist
        if email in by_email:
            prev = (by_email[email].get("status") or "").upper()
            if prev in ACTIVE_STATUSES_OKTA and status not in ACTIVE_STATUSES_OKTA:
                # keep previous ACTIVE
                pass
            else:
                by_email[email] = u
        else:
            by_email[email] = u

    for email, u in by_email.items():
        status = (u.get("status") or "").upper()
        if status in ACTIVE_STATUSES_OKTA:
            active.add(email)
        else:
            inactive.add(email)

    return by_email, active, inactive


def _index_1p(op_users: List[Dict]) -> Tuple[Dict[str, Dict], Set[str], Set[str]]:
    """
    Returns:
      - by_email: email -> user dict
      - active_emails: set of ACTIVE 1Password users
      - all_emails: set of all 1Password user emails
    """
    by_email: Dict[str, Dict] = {}
    active_emails: Set[str] = set()
    all_emails: Set[str] = set()

    for u in op_users or []:
        email = _norm_email(u.get("email"))
        if not email:
            continue
        by_email[email] = u
        all_emails.add(email)
        if (u.get("status") or "").upper() == "ACTIVE":
            active_emails.add(email)

    return by_email, active_emails, all_emails


def reconcile(op_users: List[Dict], okta_users: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Build reconciliation buckets:

    - to_deprov:
        IdP INACTIVE + 1Password ACTIVE  -> deactivate in 1Password (SCIM/CLI)
        Rows: {email, status=<1P>, idp_status=<Okta>, id=<1P user id>}

    - to_scim_onboard:
        IdP ACTIVE + 1Password ACTIVE + NOT present in SCIM
        (verified live via SCIM /Users?filter=…)
        Rows: {email, status=<1P>, idp_status="ACTIVE", id=<1P user id>}

    - to_provision:
        IdP ACTIVE + MISSING in 1Password
        Rows: {email, status="MISSING_IN_1P", idp_status="ACTIVE", id=None}

    - in_1p_not_in_idp:
        Present in 1Password but NO IdP record at all (legacy/unmanaged)
        Rows: {email, status=<1P>, id=<1P user id>}
    """
    okta_by_email, okta_active, okta_inactive = _index_okta(okta_users)
    op_by_email, op_active_emails, op_all_emails = _index_1p(op_users)

    # ---- Bucket: to_deprov (IdP inactive + 1P ACTIVE)
    to_deprov: List[Dict] = []
    for email in sorted(op_active_emails):
        if email in okta_inactive:
            opu = op_by_email[email]
            to_deprov.append({
                "email": email,
                "status": (opu.get("status") or "").upper(),
                "idp_status": (okta_by_email.get(email, {}).get("status") or "").upper(),
                "id": opu.get("id"),
            })

    # ---- Bucket: to_scim_onboard (IdP ACTIVE + 1P ACTIVE + NOT in SCIM)
    # We verify SCIM presence live so this list will clear immediately after provisioning.
    to_scim_onboard: List[Dict] = []
    for email in sorted(op_active_emails & okta_active):
        probe = scim_lookup(email)
        if not probe.get("found"):
            opu = op_by_email[email]
            to_scim_onboard.append({
                "email": email,
                "status": (opu.get("status") or "").upper(),
                "idp_status": "ACTIVE",
                "id": opu.get("id"),
            })

    # ---- Bucket: to_provision (IdP ACTIVE + missing in 1Password)
    to_provision: List[Dict] = []
    for email in sorted(okta_active - op_all_emails):
        to_provision.append({
            "email": email,
            "status": "MISSING_IN_1P",
            "idp_status": "ACTIVE",
            "id": None,
        })

    # ---- Bucket: in_1p_not_in_idp (in 1Password but NO IdP record at all)
    in_1p_not_in_idp: List[Dict] = []
    for email in sorted(op_all_emails - set(okta_by_email.keys())):
        opu = op_by_email[email]
        in_1p_not_in_idp.append({
            "email": email,
            "status": (opu.get("status") or "").upper(),
            "id": opu.get("id"),
        })

    return {
        "to_deprov": to_deprov,
        "to_scim_onboard": to_scim_onboard,
        "to_provision": to_provision,
        "in_1p_not_in_idp": in_1p_not_in_idp,
    }
