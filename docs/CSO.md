# Chief Sales Officer: workforce oversight

The CSO is included in the Cold Email installation and is its default owner-facing identity. Campaign Director still owns campaign execution. The Conversations installation opens as Conversion Specialist. Revenue Partnerships Program Manager is optional. [Meet every role](AGENTS.md).

The CSO reviews the whole business path: approved campaigns → replies → qualified conversations → booked and attended meetings → confirmed outcomes. It assigns a named executor, next action, due date and receipt requirement. It never becomes a second sender, CRM writer or consent authority.

## Included from the CSO repository

The pinned [source package](../vendor/chief-sales-officer-orgo) contains the dependency-free SQLite ledger, six review routines, ownership reference, disabled integration example and ledger tests. Its Content Studio-specific installer is excluded. The [James-specific charter](../profiles/chief-sales-officer/CHARTER.md) and identity replace upstream Attio/ClickUp/team assumptions with GoHighLevel Agent 4 ownership.

Run a read review inside the campaign container:

```bash
cd /srv/james-gtm/cold-email
docker compose --env-file .env exec -T hermes python3 \
  /opt/james-gtm/vendor/chief-sales-officer-orgo/cso/ledger.py \
  --db /opt/data/cso/pipeline.db review
```

The local ledger is a recovery and review journal. GoHighLevel remains the CRM system of record. Read the source CLI `--help` before importing normalized events. Source IDs, timestamps, verified identity and stage evidence are required. The unchanged upstream ledger uses seven fixed source labels: use `ai-go-to-market` for campaign/conversion receipts and legacy `revenue-partner` for optional Revenue Partnerships Program Manager receipts. The private integration contract records that mapping; no separate Revenue Partner deployment is assumed. Keep all business state out of Git.

## Activate the operating loop

1. Record exact account/location, source coverage, CRM IDs, channel consent, approved targets and each executor in private onboarding state.
2. The installer prepares a disabled James-specific [integration contract](../config/cso-integration.example.json) in private `cold-email/hermes/data/cso/integration.json`. Map the normalized reply ledger, relcore cards, sequencer reports and GHL outcomes into the CSO's reviewed integration contract. Keep disabled entries disabled until verified. The two ledgers are not automatically synchronized by this package.
3. Test one synthetic opportunity and a designated real test handoff. Replay duplicates, verify due work and reconcile provider receipts. Preserve sole-writer ownership.
4. Configure morning/evening and weekly reviews on the chosen runtime or host scheduler. Review routines are prompts, not installed cron jobs. Verify an actual scheduled review and owner-facing Slack delivery if selected.
5. Run daily overdue/meeting/source-coverage review. Run weekly funnel, capacity, quality and recovery review. Report unconnected sources as unknown. Forecasts, booked revenue and collected revenue stay distinct.

The CSO can request work through a verified channel or durable assignment; cross-install dispatch is not automatically wired or enabled. If a receiver or connector is unavailable, it reports the blocker and assignment artifact. A queued request is never a completed send, booking or CRM write.

## Future workforce deployment

A separate [System One Workers scope](WORKFORCE-FOLLOW-ON.md) describes a possible later experiment. The current package uses the normal two-install Hermes deployment and does not provision workers.
