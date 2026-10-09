"""GoHighLevel contacts, read-only (private integration token with contacts.readonly; never the send token).

Live: GET https://services.leadconnectorhq.com/contacts/?locationId=..&limit=100 (Version 2021-07-28), paged
with startAfterId/startAfter. Tags `trp:<type id>` (for example `trp:F6.B.1`) mark a revenue partnership.
CRM DND flags become do-not-contact restrictions. --from-file reads a saved page (tests and the sample)."""
from __future__ import annotations

import json
import os

from . import Batch

BASE = "https://services.leadconnectorhq.com"


def _pages(token: str, location: str):
    from ..http import request
    params = f"locationId={location}&limit=100"
    after = ""
    for _ in range(500):
        page = request("GET", f"{BASE}/contacts/?{params}{after}", headers={"Authorization": f"Bearer {token}",
                                                                           "Version": "2021-07-28"})
        yield page
        meta = page.get("meta") or {}
        if not page.get("contacts") or not meta.get("startAfterId"):
            return
        after = f"&startAfterId={meta['startAfterId']}&startAfter={meta.get('startAfter', '')}"


def read(from_file: str | None = None) -> Batch:
    if from_file:
        pages = [json.loads(open(from_file).read())]
    else:
        token, location = os.environ.get("RELCORE_GHL_READ_TOKEN"), os.environ.get("RELCORE_GHL_LOCATION_ID")
        if not token or not location:
            raise SystemExit("set RELCORE_GHL_READ_TOKEN and RELCORE_GHL_LOCATION_ID (install/connect.sh --ghl)")
        pages = _pages(token, location)
    b = Batch(system="ghl")
    orgs = {}
    for page in pages:
        for c in page.get("contacts", []):
            domain = (c.get("website") or "").lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
            if not domain and c.get("email") and "@" in c["email"]:
                domain = c["email"].split("@", 1)[1].lower()
            company = c.get("companyName") or ""
            if company and domain and domain not in orgs:
                orgs[domain] = {"key": f"org:{domain}", "name": company, "domain": domain, "client": False}
            name = " ".join(x for x in (c.get("firstName"), c.get("lastName")) if x) or c.get("contactName") or c.get("email") or c["id"]
            dnd = c.get("dnd") or any((v or {}).get("status") == "active" for v in (c.get("dndSettings") or {}).values())
            b.people.append({"key": c["id"], "display": name, "first_name": c.get("firstName"), "last_name": c.get("lastName"),
                             "email": c.get("email"), "phone": c.get("phone"), "org_key": domain or None,
                             "source": c.get("source") or "GHL import", "consent": {}, "internal": False})
            if dnd:
                b.dnc.append({"email": c.get("email") or "", "phone": c.get("phone") or "", "reason": "GHL DND"})
            for tag in c.get("tags") or []:
                if tag.lower().startswith("trp:") and domain:
                    b.partnerships.append({"partner_key": f"org:{domain}", "type_id": tag[4:].upper(),
                                           "contacts": [(c["id"], "")]})
    b.orgs = list(orgs.values())
    return b
