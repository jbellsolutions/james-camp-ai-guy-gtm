# Calendar, proposals, and go-to-market tools

The agent is ready to connect Calendar, Gmail, CRM, proposal, Notion, Linear,
and other reviewed business tools through an optional Composio session. The
connection is installed **off** and stays off until both a current session MCP
URL and project API key are present. Existing installations using a Composio
server ID keep a documented migration path.

The owner chooses the accounts and smallest useful action set in Composio. The
installation agent then places the private values in `.env`, runs the managed
configuration step, tests a read-only action, and reports which tools are live.
No credential belongs in GitHub, a worker profile, an A2A message, or a prompt.

## What it may do without another approval

- Read an approved calendar and suggest open times.
- Search approved email, CRM, proposal, and project records.
- Draft an email, follow-up, proposal, task, or CRM change without sending it.
- Summarize activity and recommend the next action.

## What always requires owner approval

- Send an email or message, publish content, or contact a lead.
- Book, cancel, or move another person's meeting.
- Create or modify a live CRM or project record.
- Issue a proposal, accept terms, sign, purchase, or spend money.
- Add accounts, widen scopes, or enable a new write-capable tool.

## Safe activation sequence

1. Define the business purpose, account owner, and exact allowed actions.
2. Create a scoped Composio session and copy its returned MCP URL.
3. Store the session URL and project API key only in the machine's private
   `.env` file.
4. Run `./bin/configure-managed.sh`; it enables the connector only when both
   values exist.
5. Test one read-only request, then one reversible write with explicit owner
   approval.
6. Record the connected accounts and scopes, then keep external writes behind
   the approval policy in [PERMISSIONS.md](PERMISSIONS.md).

Composio's current session-provided URL is preferred because Composio can
handle authentication, tool discovery, context, and versioning for that user.
