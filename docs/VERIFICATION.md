# Package verification · October 9, 2026

PASS: 20 local tests (13 package tests and 7 vendored CSO ledger tests) covering two-install isolation, rerun/configuration preservation, optional affiliate enablement, CSO default identity and conversion SMS routing, disabled channels before deployment, duplicate reply replay, atomic reservation across two workers, emergency-stop guard preventing watchdog resurrection, sequence-stop dependency, old/future reply cancellation after opt-out, SMS STOP/wrong-number suppression, receipt validation, unknown-outcome holds, wrong-client rejection, authenticated HTTP intake and real relcore synthetic graph/MCP behavior.

PASS: package JSON, client documentation links, profile charter/identity presence, skill frontmatter and Python/Bash syntax. Docker Compose configuration resolves against a prepared synthetic environment without starting containers. Both installs prepare from a single command with distinct paths/ports and no external account connections.

PASS: bundled relcore imports seven synthetic people, six organizations and six partnerships, generates linked cards/context for Ava, honors sample exclusion records, and exposes context tools without approval/send tools in plugin mode.

NOT RUN: Linux Docker deployment/startup, live model inference, Slack manifest API creation/owner OAuth, sequencer staging/sends/replies, GHL location/CRM writes, live SMS/STOP, booking and target backup restoration. These require James’s chosen host and scoped accounts. No campaign, SMS or invitation was sent and no billable resources were provisioned.

Package readiness is not live integration readiness. Follow ACCEPTANCE.md and record provider receipts in a private completion card.

The CSO ledger tests cover event replay/conflict, stage/identity evidence, assignment receipts, due work, timezone normalization, unknown/stale sources and ambiguous external writes. They do not establish live CRM synchronization or scheduled deployment.
