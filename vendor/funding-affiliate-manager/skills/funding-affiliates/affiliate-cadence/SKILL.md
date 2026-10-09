---
name: affiliate-cadence
description: "Run the daily affiliate rhythm: sweep for 30/60/90/180-day silence, retag lifecycle, build the morning task queue (scheduled 'check back with me' follow-ups first, then personal check-ins), draft personalized touches, batch them for one approval, and run bi-weekly/monthly cadence enrollments. Use every morning and whenever asked 'who haven't we talked to', 'who's due', or 'run the daily'."
---

# Affiliate cadence — the daily loop

**Rules of the rhythm** (config/cadence.json): touch every 14 days alternating SMS/email · offer every 30 days · quiet at 45 days silent · personal check-in at 60 · dormant + reactivation at 90 · dead + quarterly dead-lead campaign at 180 · a `next_touch_date` (they told us when) beats everything.

## Morning
1. `fam_status` → abort and alert if GHL is down or writes are stopped.
2. `fam_sweep_apply_lifecycle` → note the counts: silent 30+, silent 90+, lifecycle changes.
3. `fam_daily_queue` → personal items (cap 40/day; overflow rolls to tomorrow — say how many).
4. For each item: `fam_affiliate_brief` → draft ONE message using `knowledge/funding/05-conversation-playbook.md`:
   - `scheduled_followup`: reference what they told us (`cadence_note`) in their words.
   - `personal_checkin`: "How's it going? What can I do to help? Seen the new programs?" + one specific hook (their niche, their last deal, their source community).
   - SMS ≤ 300 chars before the auto-added "Reply STOP to opt out." Email: subject ≤ 6 words, 3 short paragraphs, one question.
5. `fam_messages_prepare(messages_json, "daily personal touches")` → `fam_action_request_approval` → post the card verbatim. Wait.
6. After the manager approves (`fam_action_approve`) → `fam_action_execute` → report live / simulated / failed counts.
7. Bulk: report `bulk_counts` (biweekly_touch, monthly_offer, onboarding, dormant_reactivation, dead_reactivation). If a standing approval covers them → `fam_standing_run_cadence`. Otherwise offer to `fam_enrollment_prepare(workflow_key, from_sweep_kind=<kind>)` and ask.

## Summary to post (5 lines)
🔥 hot (deals/replies) · 📅 follow-ups done today · 💤 newly quiet/dormant · 📤 what went out (live vs simulated) · ⛔ blocked/needs a decision.

## Don'ts
No sends without the card + approval. Don't draft generic blasts for personal items. Don't skip a scheduled follow-up — if it can't go today, reschedule it with `fam_followup_schedule` and say why.
