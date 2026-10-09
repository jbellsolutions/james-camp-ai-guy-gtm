# Ready-to-run checklist

Use this as the client launch record. The setup agent handles technical work; James provides business decisions, private credentials, and account authorization. Mark a selected feature complete only with evidence. Unselected services can stay unconnected.

## 1. Bring to setup

- [ ] Choose **Cold Email**, **Conversations & Conversion**, or **both**; decide on Revenue Partnerships Program Manager at the end.
- [ ] Choose an existing Orgo computer or a Linux VPS; provide authorized access and approve any new hosting spend.
- [ ] Provide the offer, ideal customer, exclusions, truthful proof, approved/prohibited claims, voice, and sender identity.
- [ ] Identify the decision maker, approval scope, response expectations, escalation route, and monthly operating budget.
- [ ] Supply a lead file or choose a sourcing route. Record geography, source restrictions, required fields, and a sample-acceptance rule.
- [ ] Provide a model account/key privately. The baseline uses Fireworks; a different provider is a reviewed setup choice.
- [ ] Supply an approved booking link or calendar connection and qualification questions.
- [ ] Identify existing campaigns/automations to preserve or pause so there is one sender for each action.

## 2. Install and verify the host

- [ ] Inspect OS, free memory/disk, network access, existing deployments, permissions, and occupied ports.
- [ ] Have Git, GitHub CLI, Python 3.10+, Docker/Compose, and the source installer’s recovery scheduler available on the selected Linux host.
- [ ] Allow outbound access for code/dependency/image downloads and selected provider APIs. Authenticate GitHub only where needed; a public clone needs no client token.
- [ ] Prepare the selected installs; confirm distinct names, state trees, dashboards, and A2A ports.
- [ ] Enter keys privately and restrict env files; preserve customized identity/configuration and runtime data on rerun.
- [ ] Deploy the pinned runtime; pass health and harmless model-inference checks for each enabled profile.
- [ ] Keep dashboards/intake private; configure an authenticated access route and a backup/restore point.
- [ ] Pass package tests, synthetic graph import, event replay, task reservation, and emergency-stop checks.

The default two-stack resource limits total 6 GB of container memory and 4 CPUs before the host/browser overhead. Size the selected host for actual workloads; inspect capacity before provisioning. Browser jobs share at most four screen leases. [Deployment details](DEPLOYMENT.md)

## 3. Connect cold email, if selected

- [ ] Choose **Instantly or Smartlead**; confirm the account plan permits the needed API/webhook features.
- [ ] Supply the scoped API credential privately and verify the correct account/client/campaign.
- [ ] Confirm sender domains, mailboxes, DNS access, authentication, current health, and a monitored reply inbox.
- [ ] Select and connect a real email-verification service. Reacher guidance is included; the verifier itself is an external service.
- [ ] Verify/dedupe the sample and full audience; document held, invalid, catch-all, unknown, and suppressed records.
- [ ] Confirm copy and personalization evidence; pass mechanical QC and independent Editorial on the exact renders.
- [ ] Stage the campaign paused; read back audience, copy, sender, schedule, caps, and stop-on-reply.
- [ ] Configure actual provider event authentication/normalization or reconciliation polling, and persist its watermark.
- [ ] Use a designated test address: send, receive a reply, stop the sequence, classify, and acknowledge the handoff without duplicates.
- [ ] Activate a versioned launch/reply scope covering approved artifacts, spend, windows, caps, pause thresholds, and expiry.

A provider-specific webhook/polling adapter is configured against the chosen account during setup. The bundled authenticated intake expects normalized events; it is not a preconfigured Instantly/Smartlead webhook endpoint. [Event contract](EVENTS.md)

## 4. Connect GoHighLevel and SMS, if selected

- [ ] Confirm James’s exact GHL location, scoped Private Integration/OAuth permissions, and approved field/stage mapping.
- [ ] Run the bundled GHL connection installer; verify the CLI and MCP load in the conversation runtime.
- [ ] Test authorized reads, a designated test contact upsert/readback, a unique opportunity, a conversation record, and next-owner assignment.
- [ ] Confirm a sending phone/provider and any applicable registration are ready; adopt message windows and caps.
- [ ] Record evidenced SMS consent, channel preferences, suppression/DND, and recipient time zone. Unknowns hold proactive SMS.
- [ ] Configure real inbound-message delivery/reconciliation and prevent competing GHL AI/workflows from sending twice.
- [ ] With a consented test phone, verify actual SMS send/delivery, inbound reply, context refresh, STOP, and wrong-number behavior.
- [ ] Verify contact-card context before a draft; retain answered questions, factual sources, and open commitments.
- [ ] Confirm a test booking in the actual calendar and CRM rather than inferring it from a stage change.

[GHL CLI/MCP files and setup](TOOLKIT.md#gohighlevel-cli-and-mcp) · [CRM conversation skill](../skills/crm-conversations/SKILL.md)

## 5. Add chosen options

- [ ] **Slack:** owner authorizes the workspace app; app/bot tokens, home channel, and Member-ID allowlist are configured. Authorized reply and unauthorized-user rejection both pass.
- [ ] **Data Box / BrowserBox:** fetch locked source, configure the chosen service, and validate a small permitted data job/browser action.
- [ ] **Data subscriptions:** select only providers that fit the audience; verify current API availability, account access, quota, budget, provenance, and result quality.
- [ ] **Composio:** connect only selected toolkits/accounts, inspect schemas, and run a read probe before writes.
- [ ] **PlusVibe / Consulti / additional providers:** inspect current docs and available adapters before promising an integration; create/review a skill if needed.
- [ ] **Revenue Partnerships Program Manager:** approve program terms, partner taxonomy, attribution source, and responsibilities; reuse the existing graph and communication ownership.

## 6. Activate CSO oversight

- [ ] Record verified source coverage, canonical IDs and single-writer mappings.
- [ ] Test journal ingestion and cross-install assignments; synchronization is explicitly configured.
- [ ] Verify an actual morning/evening and weekly review schedule.
- [ ] Verify the daily brief reports owners, due dates, receipts and source gaps.

[CSO activation guide](CSO.md)

## 7. Deliver and keep running

- [ ] Complete the [live acceptance record](ACCEPTANCE.md) and [completion card](../templates/COMPLETION.md).
- [ ] Record every selected connection as LIVE, UNCONNECTED, or BLOCKED, with a receipt or named next owner.
- [ ] Document current hosting, model, sequencer, mailbox, verification, CRM/SMS, and optional data-service charges from provider quotes.
- [ ] Set the agreed daily review of replies, suppression, CRM backlog, due commitments, infrastructure, spend, and caps.
- [ ] Set the weekly scorecard: actual sends, human/positive replies, qualified conversations, booked/held calls, and authoritative conversions.
- [ ] Verify recovery and provider-pause procedures. Local emergency stop does not itself pause independent provider campaigns/workflows.
- [ ] Hand James his private access instructions, last healthy version, restore evidence, and operational owner.

**Launch is complete when the selected real workflow passes.** Passing package checks establishes that the package is consistent; account authorization and live channel tests establish that James’s deployment can operate.
