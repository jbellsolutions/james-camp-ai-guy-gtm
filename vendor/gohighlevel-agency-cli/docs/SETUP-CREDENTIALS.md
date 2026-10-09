# Connecting the GHL CLI — credential setup

Two values are required. Both come from your GoHighLevel account; only you can
retrieve them. Nothing else in this repo works until they are set.

Everything is written to **`/Users/home/GHL-MCP/.env`** — the single source of truth
read by both the `ghl` CLI and the `gohighlevel` MCP server.

---

## 1. `GHL_API_KEY` — Private Integration Token

1. Log in to GoHighLevel and switch into the **sub-account** you want the CLI to drive.
2. **Settings → Private Integrations → Create New Integration.**
3. Name it something you'll recognise later, e.g. `claude-code-cli`.
4. **Select scopes.** The token can only do what you tick here. If you later hit
   `"The token is not authorized for this scope"`, open the integration in GHL and add
   the scope; if the UI won't let you edit scopes, create a new token with the full set
   and swap it in. For the smoke test to pass cleanly, tick the read scopes for every
   product you use. At minimum:

   | Want to use | Tick these scopes |
   |---|---|
   | `contacts` | contacts.readonly, contacts.write |
   | `opportunities` | opportunities.readonly, opportunities.write |
   | `calendars` | calendars.readonly, calendars/events.readonly, calendars.write |
   | `workflows` | workflows.readonly |
   | `conversations` | conversations.readonly, conversations/message.write |
   | `payments` | payments/transactions.readonly, invoices.readonly |
   | `forms` | forms.readonly, forms/submissions.readonly |
   | `social` | socialplanner/post.readonly |
   | `locations` | locations.readonly, locations/tags.readonly, locations/customFields.readonly |

   Grant only what you actually want the CLI (and agents) able to do. Read-only scopes
   are the safe default; add write scopes deliberately.
5. Copy the generated token. It starts with **`pit-`** and is ~40 characters.

### CRITICAL: agency-level vs location-level integrations

GHL has **two different kinds** of Private Integration, with **two different scope lists**:

| Created from | Scope list | Grants access to |
|---|---|---|
| **Agency view** (Settings at agency level) | ~24 scopes | snapshots, custom-menus, locations, saas, oauth, companies |
| **Inside a sub-account** (switch into the sub-account first) | much longer | contacts, opportunities, calendars, conversations, workflows, forms, payments, social, location tags/customFields … |

**`contacts.readonly` and friends are simply not present in the agency scope list.**
Ticking every box on an agency integration therefore cannot grant them — this is not a
permissions mistake, the options do not exist on that screen.

If almost everything 401s with *"The token is not authorized for this scope"* while
`locations` and `snapshots` work, you have an agency token and need a **location-level**
one. Confirm with:

```bash
/Users/home/GHL-MCP/.venv/bin/python /Users/home/GHL-MCP/scope-probe.py
```

It prints a tier-by-tier breakdown and names the diagnosis outright. A `users` endpoint
returning **"Token's user type mismatch!"** is the giveaway: the token's userType is
`Company`, not `Location`.

To fix: switch **into the sub-account** in GHL (not Agency view) → Settings → Private
Integrations → Create New. Use that token as `GHL_API_KEY`.

You can keep the agency token separately if you want snapshot/sub-account management —
the two do different jobs.

### Agency-level tokens

An agency/company-level token can enumerate its own sub-accounts with no extra config:

```bash
ghl --json locations search --limit 100
```

Pick the sub-account you want and put its `id` in `GHL_LOCATION_ID`. Note that a
location ID is still required for almost every command — `contacts`, `opportunities`,
`calendars`, and the rest are all location-scoped even on an agency token. Only
`locations search` works without one.

`GHL_COMPANY_ID` is optional; `locations search` infers the company from the token.

## 2. `GHL_LOCATION_ID` — sub-account ID

While in that sub-account, look at the browser URL:

```
https://app.gohighlevel.com/v2/location/YB8rMdFShcHGcZGW87mA/dashboard
                                        ^^^^^^^^^^^^^^^^^^^^
                                        this is the Location ID
```

It also appears under **Settings → Business Profile**. Roughly 20 characters.

> The ID shown above is the upstream author's, used here only to show the URL shape.
> Yours will differ. There is deliberately **no default** — if this is unset the CLI
> exits with an error rather than silently targeting someone else's account.

---

## 3. Write them in

Easiest — run the helper and paste each value when prompted (input is not echoed,
and the values never appear in your shell history):

```bash
/Users/home/GHL-MCP/set-credentials.sh
```

Or edit `/Users/home/GHL-MCP/.env` by hand:

```env
GHL_API_KEY=pit-your-real-token-here
GHL_LOCATION_ID=your-real-location-id
```

## 4. Verify

```bash
/Users/home/GHL-MCP/verify.sh
```

| Exit | Meaning |
|------|---------|
| `0` | Every group responded. Fully connected. |
| `1` | At least one real failure — read the output. |
| `2` | Credentials missing or still placeholders. |
| `3` | Token is **valid** but lacks scopes for some groups (see the SCOPE list). |

A `SCOPE` line means the token authenticated fine but was created without that scope
ticked — the fix is in the GHL UI, not in this CLI.

`SKIP (HTTP 403/404)` on a line means that GHL product isn't enabled on the sub-account,
or your token lacks that scope. That is **not** a CLI bug — expect it on `social`,
`payments`, and `documents` for many accounts.

If everything returns **401**, the token is wrong, expired, or was created in a
different sub-account than the Location ID points to.

---

## 5. `GHL_FIREBASE_REFRESH_TOKEN` — optional, and usually skip it

Needed **only** to *create* workflows programmatically (the public API can only read
them). Almost nobody needs this.

**It is your entire GHL login — full account access, not a scoped key, and not
revocable the way the `pit-` token is.** Treat it exactly like your password.

Prefer **Snapshots** instead: build the workflow once in the GHL UI and ship it in a
Snapshot, and sub-accounts inherit it. No token, no unofficial API, no risk.

If you genuinely need it, the DevTools snippet is in `docs/get-firebase-token.md`.
Only ever use it on your **own agency account**, never a client's.

---

## Rotating

For the default (`.env`) profile: edit `.env` and re-run `verify.sh` — both the CLI and
MCP server pick it up. For a named multi-tenant profile: `ghl profiles add <name> ...`
again with the new token (same name, overwrites). Either way, revoke the old Private
Integration in the GHL UI afterward. **Rotate any token you have pasted into a chat
window.**

---

## Adding a new business/client profile (multi-tenant)

Once one profile works, adding another sub-account (a new ConnectMed client, Revenue
Partners' own future client, or the funding business) is:

1. **Sub-account must already exist as a GHL Location.** Either it already exists, or
   create it: `./provision-location.py --business <business> --label "<name>" --phone
   "<phone>" [--snapshot-id <id>]` (dry-run by default; add `--confirm` to actually
   create it — this is a real, possibly billable write, confirm with the user first).
   GHL's create-sub-account API needs the Agency Pro plan; if it's not available,
   create the Location by hand in the GHL UI instead.
2. **Issue a location-level Private Integration Token** for that sub-account — same as
   step 1 above, but done *from inside that sub-account*, not from Agency view. This is
   the step GHL's API cannot do for you.
3. **Register it:**
   ```bash
   ghl profiles add <name> --business <revenue-partners|connectmed|funding> \
     --location-id <id> --label "<human name>"
   ```
   (prompts for the token with hidden input if `--api-key` is omitted).
4. **Verify it:** `./verify.sh --profile <name>` or
   `.venv/bin/python scope-probe.py --profile <name>`.

`ghl profiles list --business <name>` is how you (or an agent) enumerate everyone in one
business bucket — GHL's own API has no such filter, so this local registry is the only
place that grouping exists.

**Live example of "between step 1 and step 2":** `connectmed-test`
(`location_id vTkbhOREjYXj0Nf74MKC`) was created via `provision-location.py --confirm`
on 2026-08-22 and registered as a profile, but has no Private Integration Token yet —
step 2 was never finished (it was a provisioning smoke test with made-up data, not a
real client). Running anything against it fails with `Profile 'connectmed-test' has no
api_key set.` — expected, not a bug. Either finish step 2 for it (go into that
sub-account in the GHL UI and create its token), or `ghl profiles remove
connectmed-test` if you'd rather start ConnectMed's first real client fresh.
