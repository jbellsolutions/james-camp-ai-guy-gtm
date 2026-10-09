---
name: affiliate-intake-enrich
description: "Onboard a new affiliate: make sure the source tag and profile fields are set from the intake form, enrich the profile yourself with public research (their business, niche, audience, LinkedIn/Skool presence) using Super Browser, Browser Box, or the Orgo browser, write their Obsidian note, and start onboarding. Use when a new affiliate applies or is imported."
---

# Intake & enrichment (no paid enrichment services — you are the enrichment)

1. New contact from the Affiliate Intake form or an import → confirm `src:*` tag (ask the manager if unknown), `join_date`, `aff:applied`.
2. Research (public info only, 5 minutes max per person): company site via `browser-box` `read` (or `data-box` `scrape` when plain text is enough); LinkedIn / Skool profile via your Orgo Chrome session, or `super-browser` if that isn't signed in. Capture: niche, who their clients are, audience size bucket, channels they use, anything that suggests the right products.
3. Write it: `fam_note_add` (3–5 bullets, with source URLs) + update `niche`/`audience_size`/`products_of_interest` via the `ghl` MCP only if the manager approves the write prompt; otherwise leave it in the note.
4. The sweep enrolls `aff:applied` into WF-1 Onboarding (bulk, approval) and moves them to `aff:onboarding`.
5. Never store SSNs, bank statements, or credit reports. Never guess personal details.
