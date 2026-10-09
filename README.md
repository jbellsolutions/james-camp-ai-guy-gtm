# AI Guy Go-to-Market · James Camp

A complete operating system for sourcing leads, preparing and running cold email, handling replies, and continuing qualified conversations in GoHighLevel with contextual email/SMS follow-through.

**Start:** give Claude Code this repository URL and the [handoff prompt](HANDOFF.md). It reads [START-HERE.md](START-HERE.md), interviews you for the few business choices, installs on your chosen Orgo computer or DigitalOcean VPS, and verifies each connection.

| Installation | Profiles | Owns |
|---|---:|---|
| Cold Email | 8 | Strategy, data, verification, writing, independent editorial, deliverability, sequencing, email replies |
| Conversations & Conversion | 3 | Agent 4 GoHighLevel bridge, contextual relationship/SMS manager, conversion follow-through |
| Optional Affiliate Manager | +1 | Affiliate recruiting, onboarding, activation and relationship management |

Both installations work independently. Together, the email Reply Agent stops the campaign, sends an acknowledged CRM handoff, and the Relationship Manager remembers the person and prepares personalized communication. Affiliate mode extends that manager; it never creates another reply sender.

[Project charter](charters/PROJECT.md) · [Profile roster](docs/AGENTS.md) · [Workflow](docs/WORKFLOW.md) · [Deployment](docs/DEPLOYMENT.md) · [Integrations](docs/INTEGRATIONS.md) · [Acceptance](docs/ACCEPTANCE.md) · [Operator runbook](docs/OPERATIONS.md) · [Source inventory](docs/SOURCES.md)

## What ships

Pinned AI Guy GTM deployment code; twelve profile charters and identities; the public cold email master skill and its rendered-copy verifier/references; Instantly operations; a Smartlead integration skill; source-aware data intake; relationship cards/context graph engine; selected affiliate skills; GoHighLevel CLI/MCP source; optional Composio guidance; skill creator; Claude Code plugin; two-install setup script; local durable handoff ledger and authenticated intake bridge; Slack manifests and app-creation helper; synthetic acceptance tests.

## Readiness, honestly

The package installs assets and prepares the real pinned Hermes Docker runtime. External systems require James’s credentials, account consent, provider plan access and live smoke tests. Campaigns start paused. The included event bridge queues actions; agents execute and acknowledge them through selected provider tools. It is not an unattended outbound sender. Source Affiliate Manager on Orgo is drafts-only; live SMS is enabled through the scoped GHL connection only after the acceptance checklist passes.

Public handoff edition: paid-course transcripts, swipe archives and protected references are excluded. The public cold email skill covers the complete operational workflow. The original archive can be connected privately for an authorized licensed user; it is optional. Provenance is listed in [SOURCES](docs/SOURCES.md). No historical prospect lists, old campaign credentials or live routines are included.

## Local package check

```bash
python3 scripts/check.py
python3 -m unittest discover -s tests -v
python3 scripts/install.py --mode both --prepare-only --state-root /tmp/james-gtm-preview
```

Preparation does not install system software, call providers, start services or send anything. Real installation is documented in START-HERE.md.
