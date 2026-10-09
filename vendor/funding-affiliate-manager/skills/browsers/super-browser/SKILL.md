---
name: super-browser
description: Connect to and use the live Super Browser server — browser automation, scraping, Apify actors, lead sourcing, computer-use, saved agents, and the planning council. Use when asked to "ask super browser", "run super browser", "have super browser do X", "connect to super browser", "chat with super browser / hermes", or to execute any browser/scrape/automation task. One hosted server; attach by URL, never clone.
argument-hint: <what you want Super Browser to do>
allowed-tools: Bash, Read
---
> **In the Funding Affiliate Manager:** Super Browser is already attached as the `super-browser` MCP (hosted, `SUPER_BROWSER_TOKEN`). Use it for affiliate research and profile enrichment (LinkedIn/company/website lookups), and whenever you need several browsers at once. It is a tool, not the job: never use it to send or post on someone's behalf without a manager approval card. No paid enrichment services — this *is* the enrichment.

> **Being retired.** Read pages with `browser-box` and get page data with `data-box` first. Use Super Browser only
> for bulk lead lists and approval-gated writes until data-box's paid sources land.

# Super Browser — one live server, two ways in

Super Browser is a **single deployed server** at `https://167.71.241.147.nip.io`. It has the real hands:
browser-use, computer-use (Orgo), the full scrape lane (Playwright · Bright Data unlocker/SERP/datasets ·
Firecrawl · Decodo · Hyperbrowser · Steel · Airtop · Apify's 11k actors), industrial scrape, an agent
registry, fleets, a planning council, and a DAG plan executor.

**Tool calls execute on that server**, not on this machine — artifacts land in
`/opt/super-browser/.super-browser/artifacts/`. That is the point: one code path, one deployment, work
running on the infrastructure already paid for.

> **Never `git clone` Super Browser to "install" it.** Attaching by URL is the whole design. Cloning is how
> one machine ended up with 21 divergent copies and two agents confidently giving opposite answers about the
> same product.

## Way 1 — MCP (preferred, for tool-native agents)

If `mcp__super-browser__*` tools are present, use them directly — no shell, no bridge:

- `plan_browser_task` → `run_browser_task` — **plan before running** anything nontrivial
- `list_browser_providers` · `browser_doctor` — what's available and actually usable right now
- `get_browser_run` · `list_browser_runs` · `verify_browser_run` — read-only run inspection
- `approve_browser_run` / `deny_browser_run` — external writes stop here for a human
- `resources/list` + `resources/read` — provider docs and routing playbooks

Not connected yet? Add three fields to the agent's MCP config:

```json
"super-browser": {
  "type": "http",
  "url": "https://167.71.241.147.nip.io/mcp",
  "headers": { "Authorization": "Bearer YOUR_TOKEN" }
}
```

Claude Code shortcut:

```bash
claude mcp add --transport http super-browser https://167.71.241.147.nip.io/mcp \
  --header "Authorization: Bearer $SUPER_BROWSER_TOKEN"
```

## Way 2 — the chat bridge (any agent, no MCP needed)

```bash
node ${CLAUDE_PLUGIN_ROOT}/scripts/sb.mjs chat "<your request>"   # one turn, keeps context
node ${CLAUDE_PLUGIN_ROOT}/scripts/sb.mjs repl                    # continuous chat loop
node ${CLAUDE_PLUGIN_ROOT}/scripts/sb.mjs ask "<request>"         # one-shot, no history
node ${CLAUDE_PLUGIN_ROOT}/scripts/sb.mjs reset                   # clear the conversation
```

The agent picks its own tools and reports back. Heavy work (a crawl, an Apify run) legitimately takes
minutes — a long silence is the tool working, not a hang.

Or raw JSON-RPC, for anything that speaks neither:

```bash
curl -s -X POST https://167.71.241.147.nip.io/mcp \
  -H "Authorization: Bearer $SUPER_BROWSER_TOKEN" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Which tool, and why

For "which browser/scraper should I use and why" — not "do it" — invoke the `browser-ecosystem-advisor`,
`scrape-router-advisor`, or `apify-specialist` sub-agents. They read the bundled knowledge base and answer
without spending anything. This skill is for execution and general chat.

Fast routing rules the server already follows: LinkedIn/Facebook/Maps records → Bright Data datasets ·
a named platform with a maintained actor → Apify · a generic directory at volume → Firecrawl ·
anti-bot static page → Bright Data unlocker · login/multi-step → a browser lane · desktop-shaped → Orgo.

## Config (one-time per host)

`~/.super-browser.env`:

```
SUPER_BROWSER_URL=https://167.71.241.147.nip.io
SUPER_BROWSER_TOKEN=<bearer token>
```

Never paste the token into chat, a repo, or a published page.

## Is it up? Which version?

```bash
curl -s https://167.71.241.147.nip.io/health
# {"ok": true, "commit": "e6aed7f", "mcp": "/mcp"}
```

`commit` is the live SHA — compare against `origin/master`. If two agents ever disagree about what Super
Browser can do, this is the tiebreaker. The box pulls master every 10 minutes, health-checks itself, and
rolls back with a Slack alarm if new code doesn't come up, so it is normally current on its own.

## Examples

- `"scrape all the PR firms in Miami"` → discover sources → negotiate scale → industrial crawl
- `"check this product's price on Amazon vs Walmart"` → plans it, runs both lookups **in parallel**, compares
- `"search apify for a google maps reviews actor and pilot it"` → catalog search + cost-capped pilot
- `"make me a saved agent that scrapes AI-hiring companies weekly"` → creates a re-runnable registry agent

## Failure modes

- `401` → missing or wrong `SUPER_BROWSER_TOKEN`.
- `502` → the agent is restarting (~15s, often a self-deploy). Retry.
- A tool answers `"status": "unavailable"` → that provider needs a key; it degrades honestly rather than
  faking a result. `browser_doctor` says which.
