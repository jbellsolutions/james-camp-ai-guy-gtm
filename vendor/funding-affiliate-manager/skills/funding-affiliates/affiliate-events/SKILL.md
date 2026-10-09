---
name: affiliate-events
description: "Run recurring affiliate events and trainings (e.g., 'How to use the program and get more leads', weekly partnerships coaching in Skool): set the event details, invite the right segments via the Event Invite workflow, track interest from replies, and follow up with the replay. Use when planning, announcing, or following up on an event."
---

# Events & trainings

Cadence: a partner training twice a month + a weekly partnerships/affiliate-marketing coaching call in the Skool group (Skool posting happens on your Orgo desktop, approval-gated).

1. Get from the manager: title, date/time (ET), link (GHL calendar or Zoom), host. Save with `fam_campaign_note_save(kind="event")`.
2. Invite list: active + quiet + reactivated + producing + `want:event`; skip `aff:dnc` and `aff:applied`.
3. `fam_enrollment_prepare("event_invite", contact_ids_json=[...], purpose=title, custom_values_json={"next_event_title": ..., "next_event_date": ..., "next_event_link": ...})` → card → approval → execute. (WF-7 handles reminders and the replay.)
4. After the event: tag attendees (from the manager/calendar) and create follow-up tasks for anyone who asked a question; queue growth services they mentioned.
5. Skool announcement: draft the post → approval card → post it from the Orgo desktop Chrome (skill `orgo-computer`) → screenshot as proof.
