---
name: gohighlevel-cli
description: Use the bundled GoHighLevel CLI and MCP for James’s scoped contacts, opportunities, calendars and conversations.
---

This public client overlay replaces upstream machine-specific deployment notes. Read client PROJECT, TEAM-CONTRACT and crm-conversations. Install through scripts/connect-ghl.sh on the authorized Linux host. Use the persistent tool venv at /opt/data/tools/gohighlevel/.venv. Credentials come from the conversation container’s private GHL_API_KEY/GHL_LOCATION_ID environment; no other-client registry or source-local .env is included.

Begin with `ghl --help`, the specific command help and a read of James’s exact location. GHL MCP exposes ghl_catalog, ghl_help, ghl and ghl_profiles; inspect supported arguments before calling. Explicitly select the verified location/profile when available. Scoped public API only. Client workflow provisioning uses supported UI/Snapshots; no Firebase/internal workflow utilities for this client.

Agent 4 is the sole CRM writer. Resolve identity before contact creation; upsert only within adopted scope, then read back contact/opportunity IDs and stage/owner/next action. Importing an inbound message is different from sending one. Keep email provider/thread/campaign IDs and consent evidence. GHL native AI/workflows must not race the relationship agent.

Before any SMS send, re-read current thread, channel consent/DND, phone readiness, allowed local window and owner playbook. Never infer SMS permission from an email reply. Capture actual provider message/delivery IDs; on ambiguous outcome hold and reconcile rather than retry. STOP/wrong-number/complaint suppresses first. No price, payout, permission or contract change without James’s authority.
