---
name: ghl-affiliate-ops
description: "Operate the affiliate program inside GoHighLevel: find affiliates, read profiles, tag by source and lifecycle, notes, follow-up tasks, pipelines, and workflow enrollment — through the fam-core tools, with the raw ghl CLI only as a gated fallback. Use for any 'look up / tag / move / enroll / who is…' request about affiliates."
---

# GHL affiliate operations

## Which tool
| Need | Use | Gate |
|---|---|---|
| Find / read affiliates | `fam_affiliate_search`, `fam_affiliate_brief` | none (read) |
| Who's due / cohorts | `fam_sweep`, `fam_daily_queue` | none |
| Lifecycle tag + pipeline stage | `fam_lifecycle_set`, `fam_sweep_apply_lifecycle` | audited |
| Note / "check back on X" (queues a touch to the affiliate) | `fam_note_add`, `fam_followup_schedule` | audited |
| Task for the human: call about a deal, answer a question, scope a service (never messages the affiliate) | `fam_manager_task` | audited |
| Deal came in | `fam_deal_record` | audited |
| Message / enroll | `fam_messages_prepare` / `fam_enrollment_prepare` → card → approve → `fam_action_execute` | **human** |
| Anything else in GHL (calendars, forms, opportunities, custom values, workflows list) | `ghl` MCP (`ghl_catalog`, `ghl_help`, `ghl`) | writes prompt the manager |

## The data model (config/*.json is the source of truth)
- **Source tags** `src:skool|linkedin|referral|webinar|event|facebook|website|legacy-import`. Set at intake; backfill with `fam_note_add` + a lifecycle/source fix when you learn it.
- **Lifecycle tags** `aff:applied → onboarding → active → producing → quiet (45d) → dormant (90d) → dead (180d)`, `aff:reactivated` after a reply, `aff:dnc` forever. The sweep owns these; set by hand only with a reason.
- **Fields**: `last_touch_date`, `last_reply_date`, `last_deal_date`, `next_touch_date`, `cadence_note`, `deals_submitted`, `niche`, `source`, `preferred_channel`, `products_of_interest`, `services_offered`.
- **Pipelines**: *Affiliate Lifecycle* mirrors the tags; *Affiliate Growth Services* tracks funnel/reactivation/email/social/CRM help.
- **Workflows** (FAM · WF-1…WF-9): enroll, never rebuild. Copy is in custom values (`newsletter_*`, `monthly_offer_*`, `new_offer_*`, `next_event_*`).

## Rules
- The droplet's GHL credentials are for the demo location only. If `fam_status` shows a different location or `ghl_connected: false`, stop and tell the manager.
- Bulk = workflow enrollment, never hundreds of one-to-one sends.
- Numbers you report come from `fam_scorecard` / `fam_sweep` output with today's date.
