---
name: obsidian-memory
description: "Use the Obsidian vault (~/fam-vault) as the agent's memory and the relationship graph: one profile note per partner linked to tier, niche, manager, source and product hubs, call notes, review files, daily notes. Read a partner's profile before writing to them; record what you learn so the manager can open Obsidian and see what the agent knows."
---

# Obsidian vault: memory and the relationship graph

Layout (created automatically):
- `Partners/<Name> (<id6>).md` — the partner's profile. Frontmatter (tier, plan, joined, tenure, lifecycle,
  deals, manager, completeness, kickoff state, next step) and sections: Profile (a short summary), What they
  want, How they work, Open loops, Revenue plan, Background, Facts (each with its source and date), Calls,
  Manager notes, Timeline. The note is found by GHL contact id, so a rename moves it instead of starting a new one.
- Hub notes: `Tiers/`, `Niches/`, `Managers/`, `Sources/`, `Products/`. Partner notes link to them, so
  Obsidian's graph view shows partners clustered by tier, niche, manager and what their clients need.
- `Calls/<date> <Name>.md` — summary, what we learned, commitments, transcript.
- `Reviews/` — every message in a batch, in full, numbered for `approve <id> except 4, 17`.
- `Daily/YYYY-MM-DD.md` — timestamped log of sweeps, approvals, sends, replies, calls, deals.
- `Campaigns/`, `Newsletters/`, `Events/`, `Reports/` — drafts and final copy.
- Notes from before the relationship graph live in `Affiliates/`; they move into `Partners/` the first time
  the partner's profile is written.

Rules
- Read with `fam_profile_get` (or the note itself, via `fam_read("vault/Partners/...")`) before drafting to a
  partner. It tells you the next question to ask. `fam_read("vault/Reviews")` lists review files.
- Write through the tools: `fam_reply_record` (facts_json), `fam_facts_record`, `fam_call_ingest`,
  `fam_revenue_plan_save`, `fam_note_add`. They update the note, the index and the GoHighLevel fields together.
  Don't edit partner notes by hand; everything except `## Manager notes` and `## Timeline` is regenerated.
- `## Manager notes` belongs to the manager. Read it; never write in it.
- `fam_graph_query` segments the program ("Executive partners whose clients need equipment financing").
  If the index ever looks wrong, ask the operator to run `fam graph reindex` (it rebuilds it from the notes).
- Write the daily summary with `fam_daily_note`. You can't write files directly; that is deliberate.
- Never store secrets, full contact lists, health details, religion, politics, account or ID numbers.
- The vault is synced to a private git repo every 15 minutes so Justin can open it in Obsidian
  (`obsidian://open?vault=fam-vault`). Semantic search sits on top of these files later; the files stay the source of truth.
