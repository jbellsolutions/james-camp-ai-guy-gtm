# Optional follow-on: System One Workers

This is an experiment to scope after the standard Orgo/VPS installation passes acceptance. It is not required to run this repository and is not an implemented deployment option.

Candidate workforce: CSO supervisor; Go-to-Market team; Conversion Specialist and CRM/booking support; optional Revenue Partnerships Program Manager. Reuse the current charters, skills, ownership rules, context graph and receipt contracts.

Before implementation, inspect the exact System One Workers repository/version and supported runtime/API. Establish whether workers can host the pinned Hermes runtime or require a reviewed adapter. Confirm secrets isolation, shared state access, durable queue leases, schedules, callbacks, cost ceilings, shutdown and recovery. Role profiles alone do not implement distributed workers.

Proposed pilot: synthetic events first, then one designated test contact. Compare the standard deployment with a small workforce on duplicate handling, stop/opt-out latency, context continuity, assignment/receipt accountability and recovery after a worker interruption. Never run both deployments as active senders. Roll back to the standard installation before enabling real campaigns if parity is incomplete.

Deliverables for a later authorized project: verified architecture, API contract, resource/cost plan, state-migration plan, bounded pilot, operational evidence and go/no-go decision. No workers, subscriptions or new paid capacity are created by this package.
