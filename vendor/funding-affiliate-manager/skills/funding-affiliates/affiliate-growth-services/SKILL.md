---
name: affiliate-growth-services
description: "Offer and track done-for-you help that makes affiliates more productive: a funnel page, reactivating their own old leads, email campaigns, social content, and GHL/CRM help (the '7FF Affiliate Growth Kit'). Use when an affiliate asks for help, when drafting value-first check-ins, or when asked what services are in flight."
---

# Affiliate Growth Services (the Growth Kit)

Menu: `funnel` (lead-capture page in GHL) · `reactivation` (their old list, our playbook) · `email_campaigns` · `social` (content calendar/posts) · `crm_help` (GHL setup, pipelines, automations). Packaged as a GHL snapshot add-on members can buy; the agent + VA deliver it.

1. Offer it in check-ins ("Want me to put together a funnel page for you?") — value first, never pushy.
2. When they say yes (or reply triage detects `wants_service`): `fam_growth_service_queue(contact_id, service, note)` → Growth Services pipeline card (Interested) + a scoping task for the manager.
3. Scoping call → the manager moves the card; you draft the deliverable outline in the vault (`fam_campaign_note_save`).
4. Build steps that need a browser (GHL funnel builder, social scheduling) run on your Orgo desktop; anything published on the affiliate's behalf needs their explicit approval via the manager.
5. Weekly: list open service cards with owner and next step in the scorecard summary.

Pricing and whether a service is free or paid are the manager's call — never quote a price.
