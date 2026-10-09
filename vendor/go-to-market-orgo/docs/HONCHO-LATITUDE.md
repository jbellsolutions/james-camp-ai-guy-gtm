# Honcho memory and Latitude quality

Honcho and Latitude solve different problems.

- Honcho gives the agent durable understanding of the owner and business across
  sessions. Every worker gets a distinct AI peer identity; bot-authored A2A
  turns stay in separate sessions and do not rewrite the human's profile.
- Latitude shows latency, model calls, tool calls, failures, approvals, and
  delegated work so the fleet can be evaluated and improved.

Run `./bin/connect-stack.sh` from the deployment. Existing environment values
are reused without printing them.

Latitude starts in `metadata` mode. It sends identifiers only as hashes and
omits prompts, responses, tool arguments, and results. The optional `sanitized`
mode uses Hermes redaction and bounded fields; if redaction is unavailable,
content is omitted. The observer fails open so an observability outage cannot
stop the agent.

Latitude's workspace-management MCP connection remains disabled until separately
authorized. Honcho and Latitude do not grant permission to send, spend, publish,
or change production.
