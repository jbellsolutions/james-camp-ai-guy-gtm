# Operating runbook

Daily: reconcile inbound provider events and dead letters; handle stop/suppression before CRM backlog; verify inbox health; review unanswered qualified conversations and due commitments; reconcile provider sends vs receipts; check budget and caps. Director receives one shared snapshot rather than each profile polling models independently.

Weekly: report actual sent/unique human/positive reply rates, qualified conversations, booked/held calls and authoritative conversions, with source/time window/denominator. Inspect bounced/complaints/opt-outs, response latency, source quality and open grievances. Diagnose infrastructure → list → offer → copy; choose a small hypothesis test and record approved changes. Changed copy/list/settings invalidate release and editorial clearance as applicable.

If replies stop: verify inbox/ingress and campaign state before rewriting copy. If provider returns 429 known-before-acceptance, back off using provider guidance. If timeout/unknown send, hold and inspect the actual thread before any retry. If CRM fails, pause duplicate CRM writers, retry known-unsent task with identity reconciliation; never delay suppression. If SMS consent is unclear, hold SMS and continue only on an authorized channel. If screen capacity is full, queue GUI work; do not create more computers silently.

Opt-out recovery requires new authentic consent under adopted policy; reimporting a list cannot restore permission. Owner recovery after emergency stop requires reconciliation of live provider campaigns/workflows. Purges/exports use the client’s retention rules and scope.

Backups: private encrypted state/vault/env snapshots, separate from this repo; record version and restoration evidence. Updates: inspect diff, pin release, synthetic checks, target canary, health and channel smoke, then rollout. Keep last healthy deployment and database snapshot. Never use force reset or delete customer state to repair an install.
