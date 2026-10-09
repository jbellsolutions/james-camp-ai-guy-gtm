---
name: orgo-computer
description: "Use your own Orgo cloud computer (a full Linux desktop with Chrome logged into GoHighLevel, LinkedIn, and Skool): take screenshots, click, type, scroll, run bash. Use for anything the APIs can't do — building/editing GHL workflows, funnels, and snapshots in the UI, LinkedIn research and DMs, Skool posts — and to prove work with screenshots."
---

# Your Orgo computer

- It is **yours**: the "Funding Affiliate Manager" workspace on Orgo, one always-on Linux desktop. The `orgo` MCP key is scoped to that workspace — you cannot see or touch other computers.
- You live on the DigitalOcean droplet; the desktop is your hands. Hermes' local `computer_use` is disabled on purpose.
- Logged-in sessions (set up once by Justin over VNC): GoHighLevel (demo location), LinkedIn, Skool. If a site shows a login page, stop and ask the manager — never type passwords.

## Pattern
1. Screenshot first. Describe what you see before acting.
2. Act in small steps (click → screenshot → verify). Prefer keyboard shortcuts and URL navigation over hunting for buttons.
3. `bash` on the desktop is for files and quick checks, not for bypassing the UI's logins.
4. Finish with a screenshot as proof and log it in the daily note.

## Approval rules (same as everything outbound)
- Reading, researching, building drafts in GHL (unpublished workflows/funnels): allowed.
- Publishing a workflow, sending a LinkedIn DM, posting in Skool, publishing a funnel, or anything visible to others: draft → approval card to the manager → do it only after a clear yes.
- Never create, delete, resize, or clone computers or workspaces (those tools are excluded anyway).

## Common jobs
- Build WF-1…WF-9 from `config/workflows.json` in GHL's workflow builder, leave them in **draft**, screenshot each, ask the manager to publish.
- Build the Affiliate Lifecycle and Growth Services pipelines from `config/pipelines.json` (exact names), then tell the manager to run `fam ghl bootstrap --apply` (or ask to run it).
- LinkedIn: research an affiliate's profile for intake; draft DMs for approval.
- Skool: draft the weekly coaching-call announcement and event posts for approval, then post.
