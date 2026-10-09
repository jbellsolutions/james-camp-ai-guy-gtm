---
name: data-box
description: Read a public web page as clean markdown, text, HTML or its links through the `data-box` MCP, and follow slow calls as jobs. Use when you only need what a page says (an affiliate's website, a public profile, an event page), not to click or log in. For clicking, logins or screenshots use browser-box or your Orgo computer.
allowed-tools: Read
---
# data-box: what a page says

`data-box` is attached as an MCP when `DATABOX_TOKEN` is set. This agent gets three of its tools:

| Tool | Use it for | Cost |
|---|---|---|
| `scrape` | One public URL → `markdown` (default), `text`, `html` or `links` | the free direct fetch runs at once |
| `job` | Follow a slow call: `get` with its `job_id`, `wait_seconds` up to 60 | free |
| `status` | What is up and why something is down | free |

**When a page is blocked.** If the free fetch hits a challenge, a login wall or a JavaScript-only
page, `scrape` returns `blocked` saying what stopped it, and may carry a priced plan for paid
unblockers. That is an answer, not an error. **Do not pursue the paid plan**: this agent never
uses paid enrichment. Open the page with browser-box `read` or on your Orgo computer instead.

**Retries.** Pass `request_id` when you might retry; the same id returns the first job. A refused
target (loopback, private or `file:` addresses, on every redirect) stays refused; don't retry it
unchanged.

**Not available here on purpose:** data-box's `plan`, `execute` and `sources` (priced lead pulls
through paid providers). The config leaves them out; see SOUL.md.

Self-hosting a data-box: https://github.com/jbellsolutions/box-kit
