---
name: data-box
description: Get web data and lead lists through a data-box server, always plan-first — scrape a public URL, or pull a list of businesses or people (leads) by surveying every source, showing the user a priced plan, and executing it only after they approve. Use when asked to "scrape this page", "get the content of", "pull the links from", "find me N <businesses> in <place>", "build a lead list", "where can I get data on", "search the web for", "crawl this site", "extract X from these pages", or "is data-box up". For clicking, logging in or screenshots use browser-box instead.
allowed-tools: Bash, Read
---

# data-box: web data, plan first

data-box is a data server: it gets web content and records, and records what each call cost.
**You are the brain; the user is the approver.** Browsers (clicking, logins, screenshots) live in
**browser-box**, a separate server.

## The rule: four steps for anything paid

Every paid request follows the same four steps, whether you reach data-box over MCP, HTTP or the CLI:

1. **Take in the request.** What entity (business, person, property), how many, which fields
   (phone? email? website?), where, and whether the user named a source ("use Disco", "BBB only").
2. **Scope every source.** `plan` surveys them all, tier by tier. Read the survey: every candidate,
   its price, page size, whether it can run here and why not.
3. **Narrow it to a game plan.** `plan` returns lanes (ranked by records per credit x coverage x
   field fit), cells and pages, the cost in credits and dollars against the live balance, and a
   preflight: one real call per lane with sample rows.
4. **Execute only after the user approves.** Show the plan, get a yes, then call `execute` with the
   `plan_id` and `approve: true`.

**Never approve a plan on the user's behalf**, not even a cheap one, and never pass
`approve: true` without their yes in this conversation. If they want changes (fewer lanes, a lower
cap, different places), make a new plan, or pass `drop_lanes` / a lower `max_cost_usd` to `execute`.

## The tools

| Tool | Step | Use it for | Cost |
|---|---|---|---|
| `status` | — | What is up, the Firecrawl balance, plans awaiting approval, recent spend | free |
| `scrape` | — | One public URL → `markdown`, `text`, `html` or `links` | free rung; a blocked page comes back with a `plan` |
| `sources` | 2 | "Where could this data come from?" The survey alone | free |
| `plan` | 1-3 | Any paid pull: a lead list (`kind: pull`), web `search`, `crawl`, `extract`, or a scrape past the free rung | preflight only (at most 25 credits) |
| `execute` | 4 | Run a plan the user approved; call again to resume it | at most the approved amount |
| `job` | — | Follow anything slow; `results` and `export` (csv/json/jsonl) read a pull's rows | free |

## How to present a plan

Keep it short and complete. From the plan's `body`:

- **Understood:** the intake in one line (entity, count, fields, places, named sources).
- **Sources considered:** how many, by tier (`step_2_survey.by_tier`), and the notable ones that
  cannot run and why (terms to accept, not wired yet, missing fields). Apify, if listed, is the
  expensive backup's backup.
- **Alexandria browsed:** which categories were read in full and how many tools
  (`step_2_survey.alexandria`), and how many can serve (`can_serve`).
- **Game plan:** each lane with its role (base layer or top-up), whether preflight `confirmed` it,
  calls, credits, dollars and expected records (`step_3_game_plan.lanes`); lanes dropped by
  preflight and why (`passed_over`); the worst-case total, the budget, and the Firecrawl balance.
- **Preflight:** per lane, records returned, fields present, sample names, credits spent.
- **Warnings:** read every one out (an empty balance, a named source that cannot run, an estimate
  over the cap).
- Then ask: "Run it for up to $X?"

After `execute`: report unique records against the target, what each lane did, credits spent, and
the note (for example "reached the requested count", or why it stopped and that running `execute`
again resumes it). Offer the export: `job` with `action: "export"`, `format: "csv"`.

## Tiers, and why

| Tier | Sources | When |
|---|---|---|
| 1 | Firecrawl (with Alexandria's providers: Bing, Google Maps, BBB, Houzz, Apollo, ...), MoltSets, DiscoLike | First choice. Firecrawl for anything web-shaped |
| 2 | Decodo, then Bright Data | When tier 1 cannot serve |
| 3 | Apify | The backup's backup: expensive; only when nothing above fits |

The scrape ladder after the free fetch: Firecrawl → Decodo → Bright Data → Firecrawl's browser →
Hyperbrowser → browser-box. `status` and every survey say which are wired on this server.

**Lead-pull lanes for US businesses** (verified live, 2026-09): BBB search is the cheapest call (1
credit, 15 a page, no website); Bing gives name, address, phone and website (5 credits, up to 30 a
page, at most 3 pages a metro); Google Maps is one call of up to 20 per "category in city" cell.
Contact reveal (Apollo match, FullEnrich, MoltSets) runs only on the deduped shortlist, never for
discovery.

**Why a run spends less than the plan's worst case:** a cell stops at a short page or when its pages
start repeating, calls stop at the requested unique count, and no call can take the Firecrawl
balance below zero. A bigger pull is a new plan, never a mid-run change: that is how a Hermes pull
quoted at ~1,300 credits spent ~8,000 on 2026-09-28.

**Anti-patterns:** one source for a broad vertical (BBB alone misses most operators); per-record
people search for discovery; deep Maps or Bing pagination; sweeps without dedupe. The plan already
guards against these; don't talk the user into them.

## Money rules

- `max_cost_usd` on `plan` caps the whole plan, preflight included; on `execute` it approves less
  than the plan's budget, never more.
- Pass `request_id` when you might retry: the same id returns the first job instead of paying twice.
- Slow calls return a `job_id` after `wait_seconds`; poll with `job` (`action: "get"`).
- A plan expires after 24 hours. Prices and balances are re-checked by a new one.
- If the Firecrawl balance is empty, the plan says so and skips preflight: tell the user credits
  are needed before anything can run.

**Refused on purpose:** loopback, private, link-local and `file:` targets, on every redirect. Don't
retry a refusal unchanged; read its reason.

## Running your own

```bash
git clone https://github.com/jbellsolutions/data-box && cd data-box
python3 -m venv .venv && .venv/bin/pip install -e ".[databox]"
export DATABOX_TOKEN="$(openssl rand -hex 32)"   # keep it; clients send it as a Bearer token
export FIRECRAWL_API_KEY=...                      # turns on plan and execute
.venv/bin/data-box serve                          # http://127.0.0.1:8092/mcp
```

Point the plugin at it: `DATABOX_URL=http://127.0.0.1:8092/mcp` and the same `DATABOX_TOKEN`.
Paid sources bill **the account whose key is on the server**. For a server others reach over the
internet, put it behind HTTPS (Caddy); see the repo's `docs/deploy.md`.

Same tools over HTTP (`POST <server>/api/v1/<tool>`, spec at `/openapi.json`) and the CLI:

```bash
data-box plan "roofing contractors" --geo '["Austin, TX"]' --count 50 --fields '["phone","website"]'
data-box execute plan_ab12cd34 --approve true      # only after the user said yes
data-box job export job_ab12cd34 --format csv > leads.csv
```
