---
name: charm-reply-handler
description: >
  Handles replies to Charm Offensive outreach and moves them toward a booked call and a proposal —
  drafting the right response for positive, "not right now", and negative replies, plus a discovery-call
  playbook. Use when the user says "I got a positive reply, now what", "someone replied to my cold
  email/DM", "how do I respond to this reply", "book the call", "they said tell me more", "they said
  not right now", "prep me for the discovery call", or pastes/forwards a prospect's reply.
version: "1.0.0"
source: "Adapted from Jon Buchan's Charm Offensive plugin"
metadata:
  hermes:
    tags: [outreach, sales, replies, discovery-call, conversion]
    related_skills: [charm-offensive-foundation, charm-proposal, smartlead-cold-email, owned-audiences-email-reply]
---

# Charm Offensive — Reply Handler ("Conversations to Cash")

Turn replies into booked calls without losing the charm. Read the reply, classify it, respond in the
right way, then help the user run a great discovery call that sets up a winning proposal.

## Step 0 — Load voice and profile (always)

1. Load `skill_view(name='charm-offensive-foundation', file_path='references/voice-and-humour.md')`.
2. Get the user's `charm-profile.md` (offer, booking link, sign-off, proof points). Ask for it or
   build a quick one via `charm-offensive-foundation`.
3. Load `skill_view(name='charm-reply-handler', file_path='references/playbook.md')` for the exact response templates and the on-call question bank.

## Step 1 — Classify the reply

Read the prospect's actual message and sort it:

- **Positive** — they're interested / want to talk / said "yes" or "tell me more".
- **"Not right now"** — positive in tone but they can't act yet (busy, under contract).
- **Negative** — not interested. (Polite vs. rude matters — see below.)

If they asked specific questions, answer those directly and warmly *in addition to* the template.

## Step 2 — Respond in the right way (drafts in `references/playbook.md`)

- **Positive → book the call.** Thank them, propose a short (7–15 min) call, and offer a booking link
  as the easy option. If they asked "tell me more", send the brief bulleted intro (who you are, where
  based, how you help — with the light humour) *and* the booking link. Keep it short and human.
- **"Not right now" → keep the door open (3 ways).** (1) Ask to follow up in 3/6/9 months with
  "something cute/amusing/interesting" — set a CRM/diary reminder. (2) Offer your newsletter/list if
  you have one ("no worries if not — don't ask, don't get! :)"). (3) Send a LinkedIn invite to stay
  connected.
- **Negative → be gracious.** If cold emailing, ensure they're unsubscribed from future sends. If
  they're rude, don't reply. If polite, a one-liner: "Apologies, {name}. I won't contact you again.
  Best of luck with everything. Have a great week, {your name}." Don't be discouraged — everyone gets
  these; if you *only* get negatives, revisit your data, copy, and offer.

Always draft in the user's voice; keep positive responses genuinely warm and specific to what they said.

### For SmartLead users

If the lead is in a SmartLead campaign, use SmartLead MCP tools to manage opt-outs:
- `mcp_smartlead_unsubscribe_lead_from_campaign` for polite negatives
- `mcp_smartlead_unsubscribe_lead_globally` for rude/abusive replies
- `mcp_smartlead_pause_lead` for "not right now" (with a CRM note to resume later)

## Step 3 — After the call is booked: prep + run it

Use the discovery-call playbook in `references/playbook.md`:

- **Before the call:** research their website, socials, news, LinkedIn using web search; note enough to avoid silly
  mistakes and find common ground. Offer/accept an NDA for bigger clients so you can ask more.
- **On the call:** keep *them* talking (goal: gather what you need); get permission before recording;
  take notes. Get them to introduce themselves, ask about goals/ambitions and past activity, then
  softly pitch ("just thinking out loud, have you considered…"), land a small "yes" (a free mini-audit
  or "some ideas"), surface budgets/decision-makers/KPIs, and **propose sending a proposal** with a
  deadline and a booked follow-up call.
- **After the call:** send a prompt follow-up email summarising their goals/challenges, how you can
  help (link case studies), what'll be in the proposal, and when — then update the lead status.

## Step 4 — Hand off to the proposal

When the call yields a green light, hand off to `charm-proposal` to build the proposal, passing along
the goals, challenges, KPIs, budget signals, and decision-makers you gathered.

## References

- `references/playbook.md` — response templates (positive / tell-me-more / not-now / negative), the
  discovery-call question bank, and the post-call follow-up outline.