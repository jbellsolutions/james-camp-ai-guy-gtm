"""relapprove: the owner's approval service (its own OS user, its own Slack app, its own database).

It reads prepared bundles, re-checks them, shows the owner exactly what will be signed, and on the owner's
decision writes the final bundle with an HMAC signature into spool/approved/. Owners come only from the root-owned
/etc/relcore/owners.json. The agent (user trp) can read the result but can neither sign nor write approved/.
"""
