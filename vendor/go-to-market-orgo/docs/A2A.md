# Authenticated agent-to-agent network

A2A connects this agent to a Co-Founder, Operator, Revenue Partner, or other
standards-compatible agent. It is for requests, evidence, delegation, and
handoffs—not authority transfer.

## Default

Inbound A2A is installed but bound to localhost. Remote access is refused unless
a bearer token also exists. Inbound sessions receive a reduced toolset with no
terminal, approvals, external-send tools, or recursive A2A chaining. Exchanges
are rate-limited, capped at three ping-pong turns, redacted, and written to the
Hermes A2A audit log.

## Pairing

The installation agent runs `./bin/connect-a2a.sh` on each computer. Each side
gets its own incoming token and stores the other side's outgoing token. Peer
names must match the trusted identity on the receiving side. Use a private
network URL whenever possible.

Before reporting success, retrieve each Agent Card and send a harmless readiness
request in both directions. Also test that a peer request to send a message,
spend money, reveal a credential, change permission, or approve a worker is
refused or escalated.

The installer schedules a one-minute watchdog that reads the container's actual
run state and restarts it after an unexpected exit. This keeps private A2A routes
recoverable even when a small host experiences memory pressure.

## Delegation contract

Every request should include the outcome, context, constraints, expected
artifact, deadline, and evidence required. The receiving agent returns status,
artifact/evidence, unresolved risks, and a recommendation. It does not silently
inherit the sender's credentials or authorization.

Hermes protocol reference:
<https://hermes-agent.nousresearch.com/docs/user-guide/messaging/a2a>
