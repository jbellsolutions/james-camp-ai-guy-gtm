---
name: affiliate-reactivation
description: "Bring quiet, dormant, and dead affiliates back: the relationship kickoff (one personal text from the partner's named manager, in reviewed waves, then one nudge), personal check-ins for past producers, the Dormant Reactivation sequence at 90 days, the quarterly Dead-Lead campaign at 180+, and source-specific pushes (e.g., 'reactivate dead Skool leads'). Use when asked to reactivate, win back, or 'wake up' affiliates."
---

# Reactivation

## The kickoff (the 7FF reactivation)

Every quiet partner gets one text from their named partner manager, written from their own record, before
anything else. The framework is `knowledge/funding/08-kickoff-framework.md`.

1. Partners imported from Zoho (`fam import zoho`) or already in GoHighLevel (`fam kickoff enroll`) are tagged
   `fam:kickoff-pending`. They skip the bulk WF-4 / WF-5 workflows until their kickoff is sent.
2. The operator drafts a wave: `fam kickoff draft --size 250` (past producers first, then tier, recency, tenure).
   Each draft is checked: two SMS segments at most, one question, signed by the manager, no AI talk, no claims.
3. The wave's review file (`Reviews/…`) lists every message in full. Post the approval card. The manager
   approves it or holds some back (`approve <id> except 4, 17`). Held-back partners stay pending for the next wave.
4. After approval, `fam_action_execute`. Partners move to `fam:kickoff-sent`.
5. Replies go through reply triage and move the partner to `fam:kickoff-done`. No answer after 5 days:
   `fam kickoff nudge` drafts one nudge per partner, same approval path. Then the normal cadence.
6. `fam_kickoff_status` reports progress and the reply rate for each opener (A, B, C).

## The cadence plays (outside the kickoff)

| Cohort | Who | Play |
|---|---|---|
| Quiet (45–59d) | no reply/deal 45+ days | normal cadence, sharper hooks (new program, event) |
| Check-in (60–89d) | 60+ days | **personal** message drafted by you, approved in the daily batch |
| Dormant (90–179d) | 90+ days | past producers → personal; others → WF-4 Dormant Reactivation |
| Dead (180d+) | 180+ days | WF-5 Dead-Lead campaign once per 90 days; a reply moves them to `aff:reactivated` |

## "Launch reactivation for dead Skool leads"
1. `fam_affiliate_search(tag="src:skool")` + `fam_sweep` → count those with lifecycle `aff:dead` (report the number and 3 sample names).
2. Offer something of value first: a free growth-service (reactivating *their* old leads, a funnel page), the next training, what's new.
3. `fam_enrollment_prepare("dead_reactivation", contact_ids_json=[...], purpose="dead Skool leads reactivation")` → card → approval → execute.
4. Replies flow through reply triage; every reply is `aff:reactivated` automatically.

Never reactivate `aff:dnc`. Never pretend a previous conversation happened. Never guilt anyone for being quiet.
