# Agent Factory

The factory lets the Go-To-Market Partner propose a durable specialist when a
repeating workload justifies one. It ships with Prospect Research, Outbound
Campaign, Content Distribution, and Affiliate Partnerships templates.

## Flow

1. The agent states the capability gap and chooses an allowlisted template.
2. `agent_propose` writes a durable, hashed proposal. Nothing is created.
3. The owner receives the need, profile name, permissions, ongoing cost/risk,
   and recommendation.
4. The private `bin/approve-agent.sh` helper requires the exact phrase
   `APPROVE ap_...` from an interactive terminal.
5. Activation creates the profile without Slack, Telegram, business-app
   credentials, Agent Factory access, or inbound A2A of its own.
6. The parent gateway adds a bounded A2A route and restarts.

The factory exposes no delete, credential, billing, infrastructure, permission,
trust, policy, or arbitrary-command tool. Approval is one-time and bound to the
proposal hash; changing the proposal invalidates it.

Temporary research is still better handled by ordinary delegation. Create a
persistent worker only for an ongoing role with a clear owner and scorecard.
