# Sales operating model

## Pipelines and promotion gates

| Pipeline | Stages | Evidence to advance |
|---|---|---|
| Sales | new, qualified, meeting_booked, discovery_complete, proposal, negotiation, won, lost | buying intent; fit and need; booking ID; attended call notes; actual proposal ID; active commercial discussion; authoritative signed/paid evidence; explicit reason |
| Partner | identified, qualified, onboarding, activated, producing, dormant, closed | relationship fit; mutual interest; agreed onboarding; working referral asset; attributable referrals/revenue; inactivity evidence; explicit closure |
| Client | onboarding, active, expansion, referral_ready, closed | delivery handoff; active service; expressed expansion intent; verified positive outcome plus owner-approved ask; explicit closure |

One person may participate in multiple pipelines. Don't create a sales opportunity for partner-only intent. Stage changes must cite a provider event or owner decision. A booked call cannot jump to discovery complete. Missing price remains unknown. Targets never become actuals.

## Daily review

Reconcile watermarks for email inbound/outbound, LinkedIn, calendar, calls and both revenue agents. Identify duplicate events and potential identity collisions. Track all business conversations, qualified opportunities, overdue follow-ups, missing owners/dates, stale deals, missing transcripts and unsynced mutations. Prioritize explicit customer commitments, upcoming meetings and positive buying replies. Route customer-facing actions to the existing executor.

Morning Slack: three most useful revenue actions, owners and due times, then exceptions. Midday: only unresolved urgent commitments. Evening: receipts, changed stages, blockers and next-day queue. Weekly: source/window/currency, quota versus actual, conversion denominators, deal aging, forecast assumptions and corrective experiments. Unconnected sources have unknown counts. Missing data is an operational defect.

## Accountability and KPIs

| Owner | Accountable outcomes |
|---|---|
| AI Go-to-Market | eligible replies triaged, qualified handoffs, attended meetings, response time, approved campaign health |
| Revenue Partner | qualified relationships, activated partners, attributable referrals, partner follow-up completion |
| CSO | CRM coverage, overdue commitments, stage accuracy, next-action completeness, sync backlog, forecast accuracy |
| Human closer / Co-Founder | discovery decisions, proposals, commercial approvals, closes, referral asks |

Quotas are proposed from verified baselines and approved capacity; unknown baselines stay unknown. Track signed and collected revenue separately by currency, never sum unlike currencies. The owner adopts quota changes. No arbitrary quotas are seeded.

## Integrations

`integration.example.json` is the deployment contract. Confirm actual object/list/stage IDs, authorized accounts, executors and Slack destination through current readbacks. Attio is the existing design's CRM, ClickUp its task writer. The user said “ITL CRM”; resolve the exact system before live writes. The local ledger queues requests with immutable dedupe keys. It does not write external services. Build/provider-test the adapter before enabling it. Respect provider scopes and account isolation. Read both revenue agents through authenticated, owner-approved handoffs, not shared credentials.

Transcription requires an authorized recording source, transcription service and consent policy. Draft proof-page updates require the exact page and verified publication consent. No tool connection is assumed from an old backup. No external schedule is enabled by this repository alone.
