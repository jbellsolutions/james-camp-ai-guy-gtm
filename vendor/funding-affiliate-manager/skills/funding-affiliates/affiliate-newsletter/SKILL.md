---
name: affiliate-newsletter
description: "Write and send the bi-weekly affiliate newsletter: new programs and offers, partner wins, one tip for getting more leads, the next event, and a clear way to send a deal. Draft to the vault, get approval, then set the newsletter custom values and enroll the audience in the Newsletter workflow. Use every two weeks or when asked for the newsletter."
---

# Bi-weekly newsletter

**Shape** (≤ 350 words): subject (≤ 7 words) · 1-line opener · 🆕 What's new (1–3 programs/offers from `knowledge/funding/02-funding-products.md` or the manager — no rates unless the manager supplies a sourced card) · 🏆 Partner win (anonymized unless permission) · 💡 One tip to get more leads (rotate: reactivating old lists, asking CPAs for referrals, posting in communities, event follow-up) · 📅 Next training (`next_event_*`) · 👉 How to send a deal / reply to this email · CAN-SPAM footer placeholders from `06-compliance-guardrails.md`.

## Steps
1. Ask the manager for anything new this cycle (programs, wins, event date). Pull `fam_scorecard` for context — never publish internal numbers.
2. `fam_campaign_note_save(title, body, "newsletter")` → vault draft.
3. `fam_enrollment_prepare("newsletter", from_sweep_kind="", contact_ids_json=<non-DNC audience>, purpose="bi-weekly newsletter", custom_values_json={"newsletter_subject": "...", "newsletter_body": "..."})` — use `fam_affiliate_search` to build the audience (exclude `aff:dnc`; include dead only every other issue).
4. `fam_action_request_approval` → card → human approves → `fam_action_execute` (updates the custom values, then enrolls).
5. Log opens/replies next cycle via the reply triage flow.
