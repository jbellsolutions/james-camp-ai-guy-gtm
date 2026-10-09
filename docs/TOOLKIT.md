# Your toolkit

The source and operating instructions below ship with this repository. Accounts, credentials, verified adapters and a selected Linux target turn them into live connections. Follow the [requirements checklist](READY-TO-RUN.md).

| Tool | Included files | Setup remaining |
|---|---|---|
| Hermes / Orgo / VPS | [Installer](../scripts/install.py), pinned [runtime source](../vendor/go-to-market-orgo), health checks and emergency stop | Linux, Docker/Compose, private model key, capacity check, live inference and recovery test |
| GoHighLevel | CLI, MCP, scoped credential skill, connection installer | Location access, private credentials, read probe, authorized test CRM/SMS and sole-writer mapping |
| Instantly | [Operating skill and scripts](../skills/instantly-cold-email) | Account/API access, domains/mailboxes, staged readback, authenticated events/polling and test replies |
| Smartlead | [Operations skill](../skills/smartlead-operations) | Current official API/schema verification and campaign/event connection; guidance is bundled, a turnkey provider adapter is not |
| Email verification | [List charter](../profiles/gtm-list/CHARTER.md), campaign QC, verification procedure | An actual verifier account or reviewed self-hosted verifier, freshness policy and sample results; no hosted verification service ships here |
| Campaign copy | [Cold email skill](../skills/cold-email-master), rendered-copy checker, independent editorial charter | Client proof/offer, reviewed exact sequence, audience and sending release |
| Conversion context | [relcore source](../vendor/affiliate-manager-agent), [relationship wrapper](../scripts/relationship.sh) | Private card/graph state, canonical IDs, consent and CRM receipts |
| CSO | [Selected CSO source](../vendor/chief-sales-officer-orgo), [client profile](../profiles/chief-sales-officer/CHARTER.md), review routines and ledger | Verified source mappings, review schedule and accountable executors; see [CSO setup](CSO.md) |
| Reply handoffs | [Workflow ledger](../scripts/workflow.py), [normalized intake](../scripts/intake.py) | Provider-specific authenticated normalization/polling, authorized executors and reconciliation |
| Slack | [Manifests](../slack), [setup guide](SLACK.md) | Workspace app creation, owner OAuth consent, private bot/app tokens, allowed Member IDs and test |
| GitHub CLI | `gh` authentication and setup steps in [guided installation](../START-HERE.md) | Install official CLI on the chosen host, authenticate and verify repository access; the binary is not vendored |
| Composio | [CLI skill](../skills/composio-cli) | Optional official CLI install and private account/app connections; no parallel sender |
| Data Box / BrowserBox | [Sourcing skill](../skills/lead-sourcing), skills and [locked fetcher](../scripts/fetch-optional.py) | Optional source fetch, inspect dependencies, selected provider keys and bounded probe |
| PlusVibe / Consulti | Discovery guidance and [service directory](SERVICES.md) | Inspect current official API/access and build/test a skill if chosen; no preconnected MCP claimed |
| Skill creator / Claude Code | [Skill creator](../skills/skill-creator), plugin manifests, [handoff](../HANDOFF.md) | Claude Code access on setup machine; reviewed tool schemas and tests for new capabilities |
| Affiliate Manager | [Optional charter](../profiles/affiliate-manager/CHARTER.md), skills and relationship engine | `--affiliate`, partner program/terms, attribution source and approved partner playbook |

## GoHighLevel CLI and MCP

The actual implementation is bundled at [gohighlevel-agency-cli](../vendor/gohighlevel-agency-cli). The [connection installer](../scripts/connect-ghl.sh) copies it into persistent conversation state, builds its own Python venv, installs its required packages and registers MCP for the conversation profiles. This avoids modifying the host's Python environment.

After the Conversations runtime is deployed and private scoped credentials are configured:

```bash
bash scripts/connect-ghl.sh /srv/james-gtm
cd /srv/james-gtm/conversations
docker compose --env-file .env exec -T hermes \
  /opt/data/tools/gohighlevel/.venv/bin/ghl contacts list --limit 5
```

Readback must match James's designated location. Test mutations only against designated records and consented test recipients. CLI help alone proves installation, not account access. Agent 4 owns CRM writes; Conversion Specialist prepares contextual communication. Identify the authorized sender and disable competing automations before activation.

## What is intentionally separate

Model usage, email infrastructure, data subscriptions, verification, CRM/SMS charges and host capacity are purchased from selected providers. Data Box is optional; an uploaded CSV can start the same workflow. The [service directory](SERVICES.md) distinguishes packaged capabilities from discovery options. The public edition includes original public cold-email guidance; paid course archives, private client exports and production credentials are excluded.
