---
name: instantly-deliverability-audit
description: "Diagnostic audit for Instantly cold email deliverability. Checks domain auth (SPF/DKIM/DMARC), inbox health/reputation from Instantly's accounts endpoint, bounce rates, and 1% rule compliance. Use when Instantly reply rates drop, bounces spike, or as weekly/monthly health check. Trigger on 'instantly deliverability audit', 'check instantly domain health', 'instantly inbox health'."
version: 1.0.0
source: Adapted from GrowthEngineX coldoutboundskills
---

# Email Deliverability Audit

**If your positive reply rate is dropping and you don't know why, start here.**

## The 1% Rule

A healthy domain must have ≥1% overall reply rate after 200 emails sent.

Below 1% after 200+ sends = red flag. Possible causes:
- Emails landing in spam (run spam placement test)
- Domain reputation damaged
- Copy is broken (review against spam-trigger words/phrasing)
- List is wrong ICP (bounce rate >3% = list problem)
- Inbox hasn't warmed enough

Below 200 sends: too early to judge.

## When to Run

- Reply rate dropped >30% week-over-week
- Bounces spiked above 2%
- Before scaling a campaign
- Monthly as routine hygiene (Monday task in weekly rhythm)

## Audit Steps

### 0. Pre-Flight: Verify Instantly API Is Alive

**Do this FIRST.** If the API is down, every subsequent step will fail silently and the audit is a waste of time — a "no issues found" report generated while the API is actually down is worse than no report at all, since it reads as an all-clear.

```bash
curl -s -o /dev/null -w "%{http_code}" "https://api.instantly.ai/api/v2/campaigns" \
  -H "Authorization: Bearer $INSTANTLY_API_KEY"
```

200 → proceed. 401/403 → key invalid/revoked, stop and log the outage rather than silently reporting an empty audit. Learn and document Instantly's actual failure-mode response bodies the first time you hit one (e.g. an expired-plan message reads very differently from an invalid-key message, and you want to be able to tell them apart later) — until then, treat any non-200 as "cannot pull data."

**When API is down:** Still write the audit report to Obsidian. Note the outage and carry forward the last known state from the previous audit file. Do NOT go `[SILENT]` — you need to know the API is down.

### 1. Pull Inbox Inventory

```bash
curl -s "https://api.instantly.ai/api/v2/accounts" -H "Authorization: Bearer $INSTANTLY_API_KEY"
```

Check per-mailbox: warmup status, reputation, blocked status, daily sends — exact field names unverified until a real account with connected mailboxes is inspected (currently 0 connected).

### 2. Check Domain Authentication

For each sending domain, verify SPF, DKIM, and DMARC.

**No Instantly domain-health endpoint has been verified.** Check `GET /accounts` for domain-auth fields once you have a real account with connected mailboxes to inspect. Until then, use DNS directly:

Use the bundled `scripts/dns_check.py` which checks SPF, DKIM (both `default` and `google` selectors), and DMARC across any domain list. It validates that SPF records actually contain `v=spf1` (not just any TXT record) and flags mismatches automatically.

```bash
python3 scripts/dns_check.py domain1.info domain2.info ...
```

Check: SPF must include sending service, DKIM must return a record, DMARC policy should be `p=none`, `p=quarantine`, or `p=reject`.

**DKIM selector pitfall:** Google Workspace uses the `google` selector, not `default`. If `default._domainkey.{domain}` returns MISSING, also check `google._domainkey.{domain}` — that's where Google-hosted domains keep their DKIM key. `default` is the generic convention (used by MS365, self-hosted, etc.) but not by Google.

### 3. Pull Campaign Metrics

```bash
curl -s "https://api.instantly.ai/api/v2/campaigns/analytics" -H "Authorization: Bearer $INSTANTLY_API_KEY"
```

Whether this returns per-campaign or aggregate data is unverified until you have a real sending campaign to check against. Some platforms' analytics endpoints legitimately return 0 for campaigns with tracking disabled — that's not necessarily a bug, but it means you shouldn't treat a zero as proof of a problem. If it proves unreliable, fall back to lead/message-level data (see `instantly-cold-email`) as ground truth instead.

### 4. Flag Violations

- Any campaign with <1% reply rate AND ≥200 sends → **1% rule violation**
- Any inbox with bounce rate >3% → **high bounce**
- Any inbox with warmup blocked → **warmup failure**
- Any domain missing SPF or DKIM → **auth gap**

### 5. Generate Report

Output to Obsidian: `domains/cold-email/audits/deliverability-YYYY-MM-DD.md`

Format:
```
## Deliverability Audit — YYYY-MM-DD

### 1% Rule Check
| Campaign | Sent (7d) | Reply Rate | Status |
|---|---|---|---|
| campaign-name-A | X | Y% | ✅/⚠/🔴 |

### Inbox Health
| Email | Domain | Reputation | Daily Sends | Status |
|---|---|---|---|
| ... | ... | ... | ... | ✅/⚠/🔴 |

### Action Items
- [ ] Fix SPF on domain X
- [ ] Pause campaign Y (bounce >3%)
- [ ] Retire inbox Z (blocked warmup)
```

## Triage Decision Tree

| Symptom | Action |
|---|---|
| 1% rule failed | Run a spam placement test + review copy against spam-trigger words/phrasing |
| Bounce >3% | Re-verify the lead list with a real verifier. Discard all `invalid` emails — a scraper's own "verified" status is typically cosmetic and meaningfully unreliable. |
| Listed but 0 opens | Likely spam folder — run spam placement test. Note: opens will always show 0 when tracking is disabled — this row only applies to campaigns with tracking enabled. |
| OK opens, no replies | Copy issue — review and rewrite against your own reply-quality criteria |
| OK everything but still fails | Domain reputation — consider domain age, replace IP pool |
| All campaigns STOPPED with residual inbox | Pull `GET /emails` anyway — stopped campaigns can still get replies from previously sent emails. Check for unread items and positive replies that need attention. |
| **Instantly API down** | **Cannot run audit.** Write report noting the outage. Carry forward last known state from previous audit file. Flag P0: You must restore API access. Do NOT go SILENT. |

## Pitfalls

**Portable (DNS-check pitfalls, apply regardless of sending platform):**
- **Cloudflare DoH returns ALL TXT records in its Answer array** — the bundled `scripts/dns_check.py` correctly iterates all answers for SPF (finding the one containing `v=spf1`). When writing ad-hoc DNS checks, don't take `answers[0]` blindly for SPF queries — domains with `google-site-verification` + SPF will have the wrong record at index 0.
- **Google Workspace DKIM is at `google._domainkey.{domain}`**, not `default._domainkey.{domain}`. Always check both selectors before reporting DKIM as MISSING.
- **Security scanner blocks heredocs** (`python3 << 'EOF'`) — write DNS check scripts to a standalone `.py` file first, then execute.

**Instantly-specific: none recorded yet.** No mailboxes are connected and no audit has run against live Instantly data. Response-body quirks, field-name surprises, and other API specifics only surface once this has run against a real account — add entries here as they're actually discovered.

## What to Do Next

**All clean:** log it, close. **Issues found:** work the triage table above, or your own incident-response process if you have one.
