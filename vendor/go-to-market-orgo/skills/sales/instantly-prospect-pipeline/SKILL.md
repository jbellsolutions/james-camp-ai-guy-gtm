---
name: instantly-prospect-pipeline
description: "End-to-end pipeline: source leads via Apify → verify via a real email verifier → research + write custom emails → create Instantly campaign → upload → test. Use when you want to build a lead list, create personalized cold emails, and push to an Instantly campaign."
version: 1.0.0
metadata:
  hermes:
    tags: [Instantly, Cold Email, Sales, Outreach, Pipeline]
    related_skills: [instantly-cold-email]
prerequisites:
  env_vars: [INSTANTLY_API_KEY, APIFY_API_KEY]
  commands: []
---

# Instantly Prospect → Campaign Pipeline

End-to-end pipeline that sources leads via Apify, verifies them, researches each
lead, creates personalized emails, and pushes everything to an Instantly campaign.

Instantly has no built-in lead-sourcing/prospector endpoint — this pipeline sources
leads via Apify exclusively, then treats email verification as a mandatory, separate
step (a scraper's own "verified" flag is not a substitute for real verification).

## When to Use

- You want to source leads (via Apify) and create an Instantly campaign
- You're going from a niche/filter set → verified list → personalized emails → Instantly campaign

## Prerequisites

- `INSTANTLY_API_KEY`, `APIFY_API_KEY` in environment
- Your own offer and voice — this skill doesn't ship one. If your agent has a
  brand-voice/copywriting skill, use it to draft the sequence before this pipeline runs.

## Step 0: Source Leads via Apify

Actor ID: `<your-apify-actor-id>` (see `instantly-cold-email` for actor recommendations).
Key in env (`APIFY_API_KEY`). Typical filters:
- `totalResults: N` (check the actor's own max — often up to 50,000)
- `hasEmail: true`
- `emailStatusIncludes: ["verified"]` (deliverable emails only — still re-verify independently, see Step 1)
- `companyKeywordIncludes: [...]` — keywords for the niche
- `companyIndustryIncludes: [...]` — MUST use exact industry names (check the actor's input schema/error messages for allowed values)
- `seniorityIncludes: ["owner", "c_suite", "vp", "director"]`
- `companySizeIncludes: ["1-10", "11-50"]`
- `personLocationCountryIncludes: ["United States"]`

Poll via `/v2/actor-runs/{run_id}`, fetch the dataset at
`/v2/actor-runs/{run_id}/dataset/items?format=json`.

**⚠️ Industry values must be exact** — most actors reject unknown industries with a
400 error listing allowed values. When unsure, use only `companyKeywordIncludes` and
omit the industry filter.

**Coverage varies by niche and by actor/dataset.** Don't assume a niche that scraped
well once will scrape well from a different actor or a different underlying dataset —
validate with a small test run (a few hundred results) before committing to a full
pull on an unfamiliar niche.

## Pipeline Steps

### Step 1: Verify Emails

A scraper's own "verified" flag is typically cosmetic. Run every lead through an
independent verifier before it's usable:

```bash
python3 <path-to-your-verify-script> <file>.csv --json
```

Discard all `invalid` results, upload `valid` only.

### Step 2: Save the Verified List

Write sendable leads to CSV with, at minimum:
`first_name, last_name, email, company, title, city, state, verification_status`

### Step 3: Research + Create Custom Emails

Per-lead research → a custom email in your own voice/framework → resolved and ready
for upload. If you're using a separate brand-voice or copywriting skill, this is
where its output feeds in.

**⚠️ Critical rules for ALL emails, regardless of framework:**
- **Resolve any Spintax-style variation before upload.** Don't assume the sending
  platform resolves `{Hey|Hi}`-style syntax server-side — confirm first, and
  pre-resolve at generation time if it's unsupported.
- **Filter generic emails** (`info@`, `hello@`, `contact@`, `support@`, `sales@`) —
  shared inboxes have no individual decision-maker and run a disproportionately high
  hostile/unsubscribe rate.
- **Company-name fallback for greeting:** when a lead has no first name, extract a
  meaningful word from the company name (skip filler words like "the", "a", "group",
  "agency", "media").
- **Batch in chunks of 50 max** per session — see `instantly-cold-email`'s batch
  processing rule.

### Step 4: Create Campaign, Upload, Test, Notify

**4a. Create the campaign** via the Instantly web UI (no create-campaign endpoint is
documented in v2 as of this writing). Check `GET /campaigns` for existing campaigns first.

**4b. Upload leads** via `POST /api/v2/leads` — confirm the exact payload shape
against Instantly's current docs before a first real batch. Always populate every
field the API accepts rather than omitting optional-looking ones, and verify the
lead actually landed in the campaign after upload rather than trusting a 200
response alone (see `instantly-cold-email`'s Upload Verification section).

**4c. Save email sequences** — confirm the merge-tag syntax your account actually
supports before relying on it.

**4d. Configure campaign settings** via the Instantly UI: tracking, plain-text vs
HTML, reply-only stop condition, conservative schedule/volume.

**4e. Test with ONE lead first.** Confirm merge tags render correctly, the email body
displays properly (no raw unresolved syntax, no truncated text), and the lead
actually starts sending — before uploading the full batch. Use a fresh/throwaway
test address; don't assume duplicate-email handling is safe until you've checked it.

**4f. Report back:**
- Campaign ID and name
- Lead count (total uploaded, verified, filtered)
- Email samples (2-3)
- "Ready to add mailboxes and send"

## Key Pitfalls

| Pitfall | Impact | Prevention |
|---|---|---|
| Spintax-style syntax sent as literal text | Zero replies, burned leads | Pre-resolve before upload unless you've confirmed the platform resolves it server-side |
| Duplicate emails across campaigns | Leads possibly silently dropped or double-sent | Fresh emails only; test with one first |
| Lead upload payload gaps | A missing required field can silently create an orphaned/unlinked lead record that blocks future uploads of that email on some platforms | Populate every field the API accepts; verify the lead landed in the campaign after upload, don't trust a 200 alone |
| Generic emails (info@, hello@) | Disproportionate hostile/unsub rate | Filter aggressively before writing copy |
| Batch >50 leads in one pass | Quality degrades, filters get skipped under volume pressure | Chunk in 50, review samples each chunk |
| Company name contains a banned word from your own copy rules | e.g. "Staffing **Solutions**" trips a generic "solution" filter | Clean company names before embedding in email bodies |

### Plain-text rendering — verify actual output, don't trust the preview

Some platforms' render engines don't preserve normal line breaks in merge-tag
content — paragraph formatting can collapse into one block in the actual sent email
even when the composer preview looks fine. **Test with one lead and check the actual
received email, not just whatever preview the platform's UI shows.**

```
User defines filters
        ↓
Apify actor run (source + built-in verification tag)
        ↓
Independent email verification (mandatory — the actor's tag is not enough)
        ↓
Save verified list to CSV
        ↓
Research + write custom emails (batch of 50)
        ↓
Resolve any Spintax + banned-word scan + generic email filter
        ↓
Create campaign (UI) + upload leads + save sequences
        ↓
Test single lead → verify renders correctly
        ↓
Report back: "Ready — add mailboxes and send"
```
