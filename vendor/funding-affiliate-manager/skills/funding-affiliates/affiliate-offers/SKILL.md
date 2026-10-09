---
name: affiliate-offers
description: "Run the monthly offer and new-offer announcements to affiliates: pick the right segment by source, niche, products_of_interest, and lifecycle; write the offer copy; set the offer custom values; enroll via the Monthly Offer or New Offer workflow after approval. Use when the manager shares a new program/promo or the monthly offer is due."
---

# Offers (monthly + new program announcements)

- **Monthly offer** (WF-3, `monthly_offer`): due every 30 days per affiliate — the sweep lists who. Rotate the offer type: a funding program → an affiliate-growth service → an event → a partner incentive (only if the manager provides terms).
- **New offer** (WF-8, `new_offer`): when the manager says "we've got a new program". Segment by fit:
  - credit-repair pros / coaches → credit-building and 0%-intro business-credit style programs (per 02-funding-products, only what 7FF lists)
  - brokers / ISOs / merchant-services → revenue-based / working-capital programs
  - CPAs / bookkeepers → term / SBA-style programs and "tax-season cash-flow" angle
  - agencies / coaches → "fund your clients' growth" angle
- Copy: benefit to *their* clients in one line, who it fits, what to send, one CTA. No rates, approvals, or guarantees unless the manager gives a sourced program card (`fam` lint will block it anyway).

## Steps
1. `fam_affiliate_search(tag=...)` / `fam_sweep` to size segments; tell the manager the counts per segment.
2. Draft copy → `fam_campaign_note_save(kind="campaign")`.
3. `fam_enrollment_prepare("monthly_offer"|"new_offer", contact_ids_json=..., custom_values_json={"monthly_offer_subject": ..., "monthly_offer_body": ...})` → card → approval → execute.
