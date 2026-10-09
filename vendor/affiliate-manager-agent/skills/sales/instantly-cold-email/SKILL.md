---
name: instantly-cold-email
description: "Instantly.ai cold email system: campaigns, leads, Unibox replies, analytics, Apify lead scraping, and Reacher email verification. No official Instantly CLI -- raw HTTPS."
version: 1.0.0
metadata:
  hermes:
    tags: [Instantly, Cold Email, Sales, Outreach, CRM]
prerequisites:
  env_vars: [INSTANTLY_API_KEY]
  commands: []
---

# Instantly Cold Email Operations

Cold email infrastructure on Instantly.ai: campaign/lead/reply API access, batch-safe lead processing, Apify-based lead sourcing, and mandatory email verification before upload.

**This skill ships the mechanics, not a sales pitch.** Write your own offer, voice, and email sequence for your own business — this file won't do that for you. If your agent has a brand-voice or copywriting skill, use it to draft the sequence; this skill is where that copy ends up running.

**API Integration:** Instantly REST API v2, base `https://api.instantly.ai/api/v2/`, `Authorization: Bearer <INSTANTLY_API_KEY>`. No official CLI — raw HTTPS only.

## Batch Processing - Chunk the List (Work Smart, Not Hard)

**Never run the pipeline over an entire lead list in one pass.** For any list bigger
than one batch, process in CHUNKS of **BATCH_SIZE = 50** leads (raise toward 100 only
once a run is proven stable). Chunking keeps per-lead LLM personalization, Reacher
verification, and Instantly uploads inside provider rate limits, and makes the run
resumable after any error.

**Per-chunk loop:**
1. Take the next BATCH_SIZE unprocessed leads with the bundled helper:
   `python3 scripts/chunk_leads.py MASTER.json PROCESSED.txt /tmp/batch.json 50`
   (skips already-processed leads; exit code 3 means the list is finished).
2. Run the full pipeline on just that slice: qualify → verify → personalize → upload.
3. Checkpoint — append each processed lead's email to a `<campaign>-processed.txt`
   file, and note the batch counts wherever you log daily activity.
4. Pause a few seconds between chunks. Steady traffic beats bursts — exactly what a
   provider's HTTP 429 ("too many requests, back off") is asking for.
5. Repeat, SKIPPING any lead already in the processed file, until the list is exhausted.

**On repeated 429s / model errors:** STOP, log the last processed lead, and resume later
from the checkpoint. Never retry the whole list — "resume" means "continue from the
first unprocessed lead."

Rule of thumb: 4,500 leads = ~90 batches of 50, not one 4,500-lead blast. Slower on the
clock, but it finishes instead of erroring out. Instantly's own per-call lead upload
limit is unconfirmed — assume it forces batching (most sending platforms cap in the
100–1000/call range) and extend the same discipline to personalization and
verification until proven otherwise.

## Instantly API Access

No CLI — everything is raw HTTPS against `https://api.instantly.ai/api/v2/` with
`Authorization: Bearer $INSTANTLY_API_KEY`. `INSTANTLY_API_KEY` is injected via
compose from your environment file.

### Endpoints

```bash
# Campaigns
GET  /api/v2/campaigns                    # list campaigns
GET  /api/v2/campaigns/analytics          # campaign-level stats

# Unibox (replies)
GET  /api/v2/emails?i_status=1            # unread inbox items
GET  /api/v2/emails                       # filter further (thread/campaign)
POST /api/v2/emails/reply                 # body requires reply_to_uuid + message content

# Leads
POST /api/v2/leads/list                   # list/search leads
POST /api/v2/leads                        # upload leads (confirm exact payload shape against
                                           # Instantly's current docs before a first real batch —
                                           # field/nesting conventions do shift between API versions)

# Mailboxes
GET  /api/v2/accounts                     # connected sending accounts / mailbox health
```

Example call:
```python
import urllib.request, json, os
req = urllib.request.Request(
    "https://api.instantly.ai/api/v2/campaigns",
    headers={"Authorization": f"Bearer {os.environ['INSTANTLY_API_KEY']}"}
)
print(json.load(urllib.request.urlopen(req)))
```

Campaign creation and per-lead sequence/merge-tag settings are managed via the
Instantly web UI as of this writing — no create-campaign endpoint is documented in
v2. Verify settings afterward with `GET /campaigns` / `GET /campaigns/analytics`
rather than assuming the UI state matches what you configured.

There's no lead-sourcing/prospector endpoint in the Instantly API — source leads
externally (Apify, CSV, domain scraping — see below) and upload via the leads API.

## Apify Lead Scraping

API key in your environment as `APIFY_API_KEY`.

### Actors and Their Limitations

| Actor | Good for | Watch out |
|---|---|---|
| **`pipelinelabs/lead-scraper-apollo-zoominfo-lusha-ppe`** (ID: `<your-apify-actor-id>`) | Industry-filtered B2B leads with verified emails. Up to 50K/run, large database. | Industry values must be exact match (e.g. `"Staffing & Recruiting"` with ampersand). Check allowed values via error messages. |
| `compass/crawler-google-places` | Industry-filtered businesses (e.g. "employment agency") | **No emails returned** — addresses/phones/websites only. Needs separate email enrichment step. |
| `dev_fusion/Linkedin-Profile-Scraper` | Deep LinkedIn data with emails | Requires specific `profileUrls` (not search-based). Needs a pre-built URL list. |

Generic bulk "leads finder"-style actors are tempting on price but tend to ignore
their own title/industry filters and overshoot count limits — validate any new actor
against a small test run before trusting it at scale, regardless of what its listing
claims.

### Finding an Actor's Input Schema

Actor APIs don't always expose `inputSchema` directly. Get it by:
1. Browsing the actor's Apify Store page and checking its "Filters"/"Input" section, OR
2. Extracting from the error message after a failed run with an invalid enum value —
   most actors list all allowed values in the 400 response.

### Recruiter Lead Example (PipelineLabs-style actor)

```python
payload = {
    "personTitleIncludes": [
        "recruiter", "senior recruiter", "talent acquisition",
        "staffing manager", "head of talent", "director of recruiting",
    ],
    "seniorityIncludes": ["owner", "director", "manager", "vp", "c_suite", "partner", "senior"],
    "companyIndustryIncludes": ["Staffing & Recruiting"],   # exact match with ampersand REQUIRED
    "hasEmail": True,
    "emailStatusIncludes": ["verified"],
    "personLocationCountryIncludes": ["United States"],
    "totalResults": 500,
}
```

### Common Input Parameters (PipelineLabs-style actors)

| Parameter | Type | Description |
|---|---|---|
| `personTitleIncludes` / `personTitleExcludes` | string[] | Free-text job title search |
| `seniorityIncludes` / `seniorityExcludes` | string[] | c_suite, vp, director, manager, senior, entry, owner, partner |
| `functionIncludes` | string[] | engineering, sales, marketing, finance, operations, HR, IT, business_development |
| `hasEmail` / `hasPhone` / `hasLinkedin` | bool | Only return leads with that field populated |
| `emailStatusIncludes` | string[] | verified, unverified |
| `personLocationCountryIncludes` | string[] | Country names |
| `companyIndustryIncludes` / `Excludes` | string[] | **Must be exact match** — check error messages for allowed values |
| `companyKeywordIncludes` | string[] | Searches company name + description — use when the industry enum doesn't cover your niche |
| `companySizeIncludes` | string[] | 1-10, 11-50, 51-200, 201-500, 501-1000, 1001-5000, 5001-10000, 10001+ |
| `totalResults` | int | Actor-dependent whether this is actually respected — verify on a small run first |

### Niche Targeting via `companyKeywordIncludes`

When an industry enum doesn't include your target industry, use `companyKeywordIncludes`
to search company name + description text instead, paired with `companySizeIncludes`
to keep the result set tight.

### Apify API Patterns

```python
import urllib.request, json
APIFY_KEY = os.environ["APIFY_API_KEY"]

# Run actor
url = f"https://api.apify.com/v2/acts/{actor_id}/runs"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {APIFY_KEY}"}
data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(url, data=data, headers=headers, method='POST')

# Poll run status
status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
# status will be RUNNING → SUCCEEDED/FAILED/ABORTED

# Abort a runaway run (some actors ignore their own result-count limit)
abort_url = f"https://api.apify.com/v2/actor-runs/{run_id}/abort"
req = urllib.request.Request(abort_url, method="POST", headers={"Authorization": f"Bearer {APIFY_KEY}"})

# Get dataset
ds_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?format=json&clean=true&skipEmpty=true"
```

## Email Verification (mandatory before upload)

**Rule: verify EVERY email through a real verifier before uploading to Instantly. No
exceptions.** A scraper's own "verified" flag is typically cosmetic — expect a
meaningful chunk of "verified" leads to bounce or fail on a real check. Don't trust
it as a substitute for independent verification.

If you're running a self-hosted verifier (e.g. [Reacher](https://reacher.email/)),
wire it in as its own step between scrape and upload:

```bash
python3 <path-to-your-verify-script> <file>.csv --json
```

Discard `invalid` results; upload `valid` only. Any managed verification service
(ZeroBounce, NeverBounce, etc.) works the same way — the discipline is what matters,
not which specific verifier you use.

### Qualification Step (MANDATORY — Run Before Every Upload)

**Rule: scrape → qualify → verify → upload. Never upload raw scraper output.**

Use `scripts/qualify_leads.py` (bundled with this skill) to filter out:
- Generic emails (info@, contact@, support@, etc.)
- Invalid/malformed email addresses
- Placeholder or numeric-only company names
- Duplicate emails within the batch

```bash
python3 qualify_leads.py /tmp/raw_leads.json /tmp/qualified_leads.json
```

**Generic-address addresses (`info@`, `contact@`, `support@`, `media@`, `press@`,
`admin@`, `hello@`) run a disproportionately high unsubscribe/hostile rate** —
shared inboxes mean no individual decision-maker, which means guaranteed waste
regardless of how good the targeting was upstream. Filter them out before writing
copy, not after a bad reply comes in.

### Per-Lead Email Personalization

For campaigns where each lead gets a unique email body (not just merge-tag swaps):

1. Build a per-lead personalization step that generates per-lead email variants.
2. Confirm which merge-tag/custom-field syntax your Instantly account actually
   supports before relying on it — don't assume a syntax from another platform
   carries over.
3. Upload leads with the personalized content attached in whatever field Instantly
   resolves at send time.

### Custom Email Variables and Preview Formatting

When storing a complete per-lead custom email in an Instantly custom variable:

1. Store the entire researched email body in a scalar custom variable (e.g. `custom_email`).
2. Preserve paragraph structure with HTML breaks: replace each blank-line paragraph
   separator (`\n\n`) with `<br><br>` and each remaining single newline with `<br>`.
3. Set the campaign email body to exactly `{{custom_email}}` and nothing else — don't
   prepend a greeting, test text, or other body content, or Instantly will
   concatenate it with the variable.
4. Re-fetch the lead after updating and verify the custom variable contains the
   expected `<br><br>` separators.
5. Preview the resolved email in Instantly before activation — the preview must show
   distinct paragraphs, not one collapsed block.

**Why:** Instantly's variable panel may display raw newlines as paragraphs while the
rendered email preview collapses them as HTML whitespace. `<br><br>` forces visible
paragraph breaks in the rendered preview.

```python
html_body = custom_email.replace("\n\n", "<br><br>").replace("\n", "<br>")
lead_payload = {"custom_variables": {"custom_email": html_body}}
sequence_body = "{{custom_email}}"
```

## Controlled Send Verification (MANDATORY)

Don't claim a test email was sent merely because campaign activation returns HTTP 200
— activation starts the scheduler, it doesn't prove delivery.

1. Keep the campaign active long enough for the scheduler to process the lead. Don't
   pause it immediately after activation.
2. Poll `GET /emails` and/or the lead record until a sent message appears. The
   authoritative send evidence is an email record with the expected recipient,
   sender, subject, timestamp, campaign ID, lead ID, and thread ID.
3. Only after that record exists should you report the message as sent.
4. If the message doesn't appear, report it as queued/not confirmed — not sent.

## Upload Verification (MANDATORY After Every Upload)

**Rule: after uploading leads, verify the count landed.** Some cold-email platforms'
upload APIs are known to return success while a subset of leads silently fail to
appear — verify regardless of which platform you're on:

1. Upload leads via `POST /api/v2/leads`.
2. Immediately re-query the campaign's lead count.
3. If the count doesn't match what was uploaded, re-upload the full batch — don't
   assume deduplication is automatic unless you've confirmed it.
4. Only then proceed to start the campaign.

## Auto-Reply Daemon (Draft-to-Slack)

`scripts/instantly_reply_daemon.py` polls the Unibox, classifies replies, and drafts
responses for human approval — **it never auto-sends.**

- Polls `GET /emails?i_status=1` on its own schedule (a Hermes cron, typically).
- Classifier buckets each reply: `ooo`, `hostile`, `unsubscribe`, `dead`,
  `positive_interested`, `positive_referral`, `negative_notfit`, `neutral`.
- Positive replies get a DeepSeek-drafted response, printed as `__DRAFT__:{json}` for
  a human to review and approve before anything sends — deliver it to Slack, a
  dashboard, wherever your operator actually looks.
- State (which message IDs have been handled) lives in its own state file, separate
  from any other platform's reply daemon — running two daemons against two different
  platforms never collide.
- Set `BUSINESS_NAME` and `BOOKING_URL` env vars — the daemon reads both for draft
  copy (falls back to generic text / no link if unset).

**If you're cloning this onto a second agent that shares the same
`INSTANTLY_API_KEY` as another live agent:** both daemons will independently poll and
classify the same inbox, each with its own state file and no shared view of "already
handled." Harmless as long as only one cron is enabled at a time — risky if both run
unattended (see the README's "Cloning onto a shared external account" note).

### Reply Approval Workflow

1. **Detection**: daemon polls the inbox, classifies replies.
2. **Draft generation**: DeepSeek drafts a response using your business context.
3. **Notify**: deliver the draft to wherever a human will see and act on it.
4. **Approval**: a human explicitly approves (and can edit) before anything sends.
5. **QC pass (recommended)**: run the draft through whatever copy/tone check you use
   before sending, if you have one — this skill doesn't ship one itself.
6. **Sending**: `POST /api/v2/emails/reply` with the approved `reply_to_uuid` + body.

```python
import json, os, urllib.request

payload = {
    "reply_to_uuid": "uuid-of-the-email-being-replied-to",
    "body": {"text": "Your reply text here"}
}

req = urllib.request.Request(
    "https://api.instantly.ai/api/v2/emails/reply",
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {os.environ['INSTANTLY_API_KEY']}",
        "Content-Type": "application/json",
    },
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    print(json.load(resp))
```

## Account Consolidation (for hitting volume targets)

When a single campaign can't hit its daily send target due to inbox count,
consolidate inboxes from paused/low-priority campaigns. A common per-inbox cap is
~15 sends/day (e.g. Google Workspace) — check your own provider's actual limit.

**Quick math:** `target_sends ÷ per_inbox_daily_cap = minimum inboxes needed`.

1. Identify source campaign(s) to pull mailboxes from (typically paused/lower-priority).
2. Connect mailboxes to the target campaign via `GET /accounts` to find candidates,
   then the UI (no bulk-reassignment endpoint confirmed as of this writing).
3. Pause the source campaign.
4. Verify via `GET /accounts` / `GET /campaigns` that the mailbox count actually moved.

## Daily Stats Reporting

When generating a per-campaign daily stats report:

```
Cold Email Daily — [Day, Mon Date]
Campaign: [name] (#[id])

Sent: X | Opens: Y (Z%) | Clicks: C (D%) | Replies: R (E%)
Positives: P (F% positive reply rate)
Bounces: B | Unsubs: U

[If any positive replies today, list each:]
pos reply — "Name" (email): "[first 80 chars of reply]"
```

**Skip delivery entirely when there's nothing to report:** no new replies today, no
new sends, and all campaigns are in a terminal state with no queued activity. The key
signal is **inbound replies today**, not campaign status alone — a STOPPED campaign
with a fresh reply still needs to be reported; an ACTIVE campaign with a completed
sequence and zero replies today doesn't.

When campaigns are stopped/paused with no activity, still report the zeros and a lead
status snapshot rather than going silent — you need to know the state even when
nothing is moving.

## Pitfalls

- **Activation 200 is not delivery confirmation.** Always verify the actual `/emails`
  record before claiming success.
- **Pausing immediately after activation can prevent the first send.** Leave the
  campaign active during the verification window.
- **Campaign-level analytics may remain empty or lag** for campaigns with tracking
  disabled. Prefer the message-level `/emails` record and lead counters as ground
  truth over an analytics endpoint that might legitimately return zero.
- **Security scan blocks `pipe_to_interpreter` patterns** (e.g. piping a CLI/script
  into `python3 -c`) and heredocs (`python3 << 'EOF'`). Write scripts to a file and
  execute the file instead.
- **Security scan blocks unicode status markers in Python heredocs/scripts** —
  emoji with variation selectors can trigger a `variation_selector` rule. Use ASCII
  alternatives like `[NEW]`, `[DONE]`, `[FAIL]`, `[WARN]`.
- **Apify residential proxy costs add up** — use a datacenter proxy for non-LinkedIn
  scrapes.
- **Some Apify "leads finder"-style actors ignore their own count/title filters** —
  monitor the run's charged-event count and abort manually once you have enough;
  don't trust the actor to stop itself.
- **Google Maps-style scrapers return no emails** — only business name, address,
  phone, website. Needs a separate email-enrichment step.
- **Apify API key can go invalid silently** ("user or token not found"). If all Apify
  calls return 401, generate a fresh token and update `APIFY_API_KEY`.
- **Apify actor search is account-scoped** — `v2/acts?search=` only returns actors
  available to your account, not the full Apify Store.
- **PipelineLabs-style industry enums must be exact** (e.g. `"Staffing & Recruiting"`,
  not `"staffing and recruiting"`). Error messages list valid options.
