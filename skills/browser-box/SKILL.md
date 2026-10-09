---
name: browser-box
description: Read, fetch, screenshot, click through or log into any web page through a self-hosted browser, hand it a whole browsing goal, and stand that browser up on a VPS when it isn't running yet. Use when asked to "read this page", "what does this site say", "get the data from", "screenshot this", "fill in this form", "click through", "log in and check", "scrape", "go find out", or when a WebFetch was blocked, returned JavaScript instead of content, or hit a bot check. Also use for "is the browser box up", "start the browser box", "deploy browser-box".
allowed-tools: Bash, Read
---

# browser-box — one browser, one door

A **single gateway** in front of **one** self-hosted Steel browser, over MCP. **You are the
brain**, the box is the hands. Two models can run in it, both opt-in: Jev (behind `act`) only
picks which element a step means; Browser-Use (behind `task`) plans steps for a goal you hand
over. Neither decides what you are trying to do.

Repo: `https://github.com/jbellsolutions/browser-box`

---

## Part 1 — Using it

### The tools

| Tool | Use it for | Cost |
|---|---|---|
| `fetch` | **Try this first.** Plain HTTP GET — server-rendered HTML, JSON, APIs, RSS, docs | free, instant |
| `read` | The real browser. Use when `fetch` came back empty or unrendered | one browser slot |
| `session` | Persistent cookies/profile — how logged-in work is done | free |
| `act` | Drive the browser in plain-words steps you plan: open, click, type, scroll | TypeSafe decisions |
| `task` | Hand a whole goal to an agent: `surface="browser"` (Browser-Use, this box's browser) or `"computer"` (an Orgo desktop) | model tokens, reported per task |
| `computer` | A full Orgo cloud desktop you drive yourself: screenshot → decide → click/type/key/scroll/bash | Orgo, per hour |
| `status` | What is up, what is down, why, and what recent calls cost | free |

`act`, `task` and `computer` are **listed only when the box has them configured**, and `task`
lists only the surfaces it has. If you don't see one, this box doesn't have it — `status`
says so. There is no provider catalog, no readiness
walkthrough, no plan/verify/resume, no doctor variants. **If a tool is listed, it works.** If it
can't work right now, `status` says so in one line with the reason.

### The one rule that saves the most time

**`fetch` before `read`, every time.** Most pages are server-rendered; `fetch` answers them
instantly and for free. `read` boots a browser and holds the single lane — **one browser job
runs at a time on the host**, so a second caller waits. Burning that slot on a page `fetch`
could have answered is the main way to make this feel slow.

Escalate to `read` when `fetch` returns almost no text, returns a shell of `<script>` tags,
or returns a bot-check page.

### Clicking and typing: `act` or `task`?

**Measured (5 jobs × 3 runs):**
- `act` went 3/3 on forms, pagination, cookie state and a React to-do app, in 0.5–5 s.
- `task` took 30–130 s and failed the cookie job 2 of 3 times and the to-do app 3 of 3.
- Default to `act`. `act`'s one miss: asked for the first search result on Wikipedia, it clicked a red
"page does not exist" link. Read each step's `did` and correct it in the next turn.

**`act` when you can plan the steps.** Say each step in plain words — `"open https://…"`,
`"click the Pricing link"`, `"type 'running shoes' into the search box and press enter"` — up
to 4 joined by `then`. Jev picks the element in ~0.3 s; you see every step's outcome.
- `needs_clarification` → it wasn't sure which element you meant: answer `act(pick=<option>)`.
- `needs_confirmation` → the step looks hard to undo (buy, delete, send, post): answer
  `act(confirm=true|false)`. Nothing risky runs unconfirmed.
- It returns the URL and title, not the page's text: follow with `read(url)` to read it
  (a fresh load, so it will not show what you typed into a form).
- The tab stays where you left it between calls.

**`task(surface="browser")` when you would rather hand over the goal.** Browser-Use plans
each step with its own model. You get the answer, every step, the URLs, tokens and cost.
- A job takes ~30–130 s and under a cent; hand over what you would
  otherwise spend many turns steering.
- It works in a tab of its own and never touches `act`'s tab. Its tab closes when it finishes:
  `read(final_url)` to look again.
- **It keeps running if you stop waiting**, holding the browser, until its `timeout_seconds`.
  Call `task(cancel=true)` to stop it; the stopped task still reports what it did.
- After a `session` login, a task can act as that login. Only hand it goals on logged-in
  sites you would let a web page steer.

### Computer use (Orgo)

`computer` is a whole Linux desktop **off this box**, with a browser and a shell. **You are the
eyes:** call `computer(action="screenshot")` — it comes back as a real image you can see — then
act on pixel coordinates from that image, then look again. Pass `screenshot_after: true` on an
action to get the next image in the same call.

- `scroll` needs `x` and `y`; without them Orgo warps the pointer to the top-left corner.
- `bash` is a real shell on that computer, inside the Orgo account.
- **A computer bills until it is stopped.** There is no auto-stop. Finish with `action="stop"`.
- One job drives a given computer at a time; a second waits or is told it is busy. A busy
  computer never blocks the browser — they are separate lanes.

Can't see images, or the goal is long? `task(goal, surface="computer")` hands it to Orgo's own
computer-use agent and returns its answer. You lose sight of each step, so prefer `computer` when you can drive.
Orgo ignores step limits (its loop caps at 250); `timeout_seconds` is the real bound, and
hitting it closes the stream, which aborts the run.

### Screenshots cost a second page load

`read(url, screenshot=true)` runs a **separate** browser navigation. Two consequences:

1. On a page that changes between loads, the picture and the text may not match.
2. That second navigation is **not** redirect-checked (the text is).

Ask for a screenshot when the picture is the evidence — not by default.

### Sessions (logged-in work)

```
session(action="create")   -> session_id + devtools_url
session(action="list")
session(action="release", session_id="...")
```

Everything is bound to loopback, so a human signing in by hand must tunnel first:
`ssh -L 3000:127.0.0.1:3000 <host>`, then open the `devtools_url`. Cookies persist for later
`read` calls until the session is released. Don't create a session for a one-off public read —
`read` is cheaper and releases itself.

### Refusals are answers, not bugs

Every URL is checked before any connection is made. Refused: loopback, private ranges,
link-local, cloud metadata, and obfuscated forms (`0x7f000001`, `2130706433`, `127.1`).
Hostnames are resolved and **every** returned address checked. Each redirect hop is cleared
before it is followed, and the browser is handed the **cleared final URL**, not the one asked
for.

If you get `{"error": "refused: ..."}` the target is internal and the guard worked. Report it
plainly. **Do not try to route around it.**

If you get a busy-lane error, another job holds the browser. Wait, or use `fetch`. If it says
a browser task holds it, `task(cancel=true)` stops that task.

### When something fails

Call **`status` before concluding a capability is missing.** It reports a component that is
down as down, with the reason, and lists what still works (`fetch` and `status` always do).
An unreachable box and a broken browser are different problems with different fixes.

---

## Part 2 — Connecting to it

All three routes hit the same gateway, the same tools, the same token.

### MCP (preferred)

```bash
claude mcp add --transport http browser-box https://your-box/mcp \
  --header "Authorization: Bearer $BROWSER_BOX_TOKEN"
```

Or a project `.mcp.json` — both expansion forms are verified against Claude Code:

```json
{
  "mcpServers": {
    "browser-box": {
      "type": "http",
      "url": "${BROWSER_BOX_URL:-http://127.0.0.1:8080/mcp}",
      "headers": { "Authorization": "Bearer ${BROWSER_BOX_TOKEN}" }
    }
  }
}
```

> `claude mcp list` prints the **raw** manifest text, not the expanded value. A literal
> `${...}` in that output is not a fault.

### CLI

```bash
pipx install ./cli          # from a clone; git+https needs auth while the repo is private
bb login --url https://your-box --token <BB_TOKEN>

bb status
bb fetch -t https://example.com
bb read  -t -s -o shot.jpg https://news.ycombinator.com
bb session create
bb act "open https://example.com then click More information"
bb task --surface browser "find the top story on news.ycombinator.com and its comment count"
bb task --cancel
bb tools
```

`bb ask "<goal>"` and `bb chat` run a model **in the CLI, on this machine** (needs
`OPENROUTER_API_KEY`). The box still has no brain in it. Everything else needs no key.

### Plugin

```
/plugin marketplace add jbellsolutions/browser-box
/plugin install browser-box@browser-box
```

Set `BROWSER_BOX_URL` and `BROWSER_BOX_TOKEN` first.

---

## Part 3 — Spinning it up

**Check first.** `bb status`, or `curl -fsS https://your-box/health`. A box that is already
running does not need provisioning, and `make up` on a live host is safe but pointless.

### Host requirements

**2 vCPU / 4 GB, Ubuntu 24.04.** Not 1 vCPU / 2 GB — Steel's Chromium sits at ~686 MB and
climbs to ~895 MB within a dozen page loads, which is how a 2 GB box with no swap ends up
OOM-killing a browser instead of failing loudly.

```bash
# Docker, swap, firewall
curl -fsSL https://get.docker.com | sudo sh
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile \
  && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo ufw allow 22 && sudo ufw allow 443 && sudo ufw --force enable
```

### Bring the stack up

```bash
gh repo clone jbellsolutions/browser-box && cd browser-box
cp .env.example .env
make token                      # paste the value into BB_TOKEN in .env
chmod 600 .env
make up                         # builds the gateway, pulls Steel, waits for health
make status
```

`make` targets: `up` · `down` · `status` · `logs` · `logs-steel` · `restart-browser` (the one
recovery action for a wedged browser) · `test` · `plugin` · `smoke` · `token` · `venv`.

### Lock down egress — not optional

The gateway vets what it sees, but once Steel has a URL **Chromium does its own DNS and its
own connecting**. Deny it everything private except the gateway:

```bash
STEEL_NET=$(docker network inspect browser-box_box -f '{{(index .IPAM.Config 0).Subnet}}')
for range in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 127.0.0.0/8; do
  sudo iptables -I DOCKER-USER -s "$STEEL_NET" -d "$range" -j DROP
done
# ORDER MATTERS: -I prepends, so this ACCEPT must go in LAST to sit ABOVE the DROPs.
sudo iptables -I DOCKER-USER 1 -s "$STEEL_NET" -d "$STEEL_NET" -j ACCEPT
sudo iptables -L DOCKER-USER -n --line-numbers | head   # ACCEPT must be line 1
sudo apt-get install -y iptables-persistent
```

### TLS

Caddy on the **host**, not in compose, so a stack restart never drops TLS:

```bash
sudo apt-get install -y caddy   # or the official repo: caddyserver.com/docs/install

# Substitute the domain at install time. `BB_DOMAIN=x cp ...` does NOT work: cp does no
# substitution, and Caddy reads {$BB_DOMAIN} from the caddy SERVICE's environment, not
# from the shell that copied the file. An unset value yields an empty site address.
sudo sed "s|{\$BB_DOMAIN}|box.example.com|" Caddyfile | sudo tee /etc/caddy/Caddyfile >/dev/null
sudo systemctl reload caddy
```

### Prove it

```bash
make smoke
```

Lists the tools, calls `status`, reads a real page, asserts that obfuscated loopback is
refused, asserts that a public redirect into loopback is refused, and drives the endpoint
with a **real MCP client** (initialize, session headers, SSE) on both `/mcp` and `/mcp/`.
If `make smoke` passes, the box works. If it doesn't, the failing line names what broke.

### Pin the image before production

```
STEEL_REF=@sha256:7a161b95e8a9b20ddc2f87d380c61636bb13507f7fe99fd4704cb105c5478f99
```

That digest is the OCI image index covering **both** linux/amd64 and linux/arm64. Pin the
manifest-list digest, never a single architecture's.

---

## What it deliberately does not do

- **No brain in the box by default.** A model inside the tool, in a different body from the
  hands, is the design that failed twice. The calling agent decides. `task` is the one opt-in
  exception, and it only plans the steps of a goal you hand it.
- **No second browser.** Browser-Use is an *agent* that needs a browser, not a browser. It
  attaches to this Steel over CDP, like Jev — one engine, two steering wheels.
- **No concurrency.** A single local Chromium is not concurrency-safe: running jobs in
  parallel produced dead CDP websockets and loop errors. The lane lock is a bug already paid
  for, not caution.

### Known limits, stated plainly

1. **DNS rebinding** — a name that checks public can resolve private a moment later.
2. **A target that answers the pre-flight differently from the browser.**
3. **`read(screenshot=true)`** — the picture's navigation is not pre-flighted by the gateway.
   The in-browser guard refuses it instead, and `read` withholds the picture when the guard
   is down. The host egress rule above is the backstop.
4. **Steel can reach its own loopback** — no network policy stops a container talking to
   itself. This is why Steel holds nothing worth stealing and why the bearer token matters.

> **Never clone browser-box to "use" it** — attach by URL. One deployment, one code path,
> work running on the box you already pay for. Clone only on the host you are deploying to.
> Cloning to "install" is how the last system ended up with divergent copies giving opposite
> answers about what worked.
