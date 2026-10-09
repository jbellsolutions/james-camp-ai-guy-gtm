#!/usr/bin/env python3
"""Auto-reply daemon for Instantly inbox. Forked from auto_reply_daemon.py (SmartLead) — polls, classifies, drafts for approval.

Does NOT auto-send, same as the SmartLead version. Classification/draft-generation/handler logic is
identical to auto_reply_daemon.py by design; only the fetch/send calls differ (Instantly REST vs
SmartLead CLI). See instantly-cold-email skill for the verified/unverified endpoint list this depends on.

VERIFIED 2026-07-29: GET /emails?i_status=1 returns {"items": [...]}, confirmed against the live API
(0 items — 0 mailboxes connected). instantly_api() sends a browser-like User-Agent; Cloudflare 403s
(error 1010) on urllib's default UA. Still UNVERIFIED: individual item field names (from_email/body/
subject/id), the thread_id filter param on get_messages(), and the reply_to_uuid send path — Instantly
has never produced a real reply through this integration. Run --once against a real reply before
trusting this in production, and fix field names in get_unread()/get_messages()/handle_positive() if
they don't match once real data arrives.
"""

import json, os, re, html, time, sys
from datetime import datetime, timezone
import urllib.request, urllib.error, ssl

# ─── Config ────────────────────────────────────────────────
INSTANTLY_API_KEY = os.environ.get('INSTANTLY_API_KEY', '')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
BOOKING_URL = os.environ.get('BOOKING_URL', '')
BUSINESS_NAME = os.environ.get('BUSINESS_NAME', 'our team')
API_BASE = "https://api.instantly.ai/api/v2"
STATE_FILE = "/opt/data/scripts/instantly_reply_state.json"
DRAFT_FILE = "/tmp/instantly_reply_drafts.json"
POLL_INTERVAL = 60
ctx = ssl.create_default_context()

# ─── State ──────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"replied_message_ids": [], "hostile_senders": [], "unsub_senders": []}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True, file=sys.stderr)

# ─── Instantly REST wrappers ──────────────────────────────────
# No official CLI exists for Instantly (raw HTTPS only) — this is the single call-site all four
# platform functions route through, mirroring how smartlead() was the single call-site in the original.
def instantly_api(method, path, payload=None, timeout=30):
    url = f"{API_BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {INSTANTLY_API_KEY}",
            "Content-Type": "application/json",
            # Cloudflare 403s (error 1010) on urllib's default "Python-urllib/x.x" UA —
            # confirmed via curl comparison on 2026-07-29 (curl passes with any UA, urllib
            # doesn't without this). Not a real auth failure; don't chase 401/403 handling
            # for this specific case.
            "User-Agent": "Mozilla/5.0 (compatible; ai-guy-go-to-market-hermes/1.0)",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        log(f"  Instantly API {e.code} on {method} {path}: {body[:200]}")
        return {"error": True, "status": e.code, "body": body}
    except Exception as e:
        log(f"  Instantly API error on {method} {path}: {e}")
        return {"error": True, "body": str(e)}

def get_unread():
    """Get all unread inbox items. VERIFIED 2026-07-29: GET /emails?i_status=1 wraps as {"items": [...]}."""
    result = instantly_api('GET', '/emails?i_status=1')
    if isinstance(result, dict) and result.get('error'):
        return []
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        items = result.get('items', result.get('data', []))
    else:
        items = []
    # The unread endpoint can include our own sent messages as well as inbound
    # replies. ue_type=2 is the verified inbound-reply marker.
    return [item for item in items if isinstance(item, dict) and item.get('ue_type') == 2]

def get_messages(thread_id):
    """Get message history for a thread. Wrapper shape assumed {"items": [...]} per get_unread()'s
    verified response — the `thread_id` filter param itself is still UNVERIFIED, confirm on first real use."""
    result = instantly_api('GET', f'/emails?thread_id={thread_id}')
    if isinstance(result, dict) and result.get('error'):
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get('items', result.get('data', []))
    return []

def send_reply(reply_to_uuid, email_body):
    """Send a reply via POST /emails/reply. Body field name unverified — confirm on first real send."""
    payload = {
        "reply_to_uuid": reply_to_uuid,
        "body": {"text": email_body},
    }
    result = instantly_api('POST', '/emails/reply', payload)
    if isinstance(result, dict) and result.get('error'):
        return False
    log(f"    Sent (Instantly confirmed)")
    return True

# ─── DeepSeek Reply Generator ───────────────────────────────
# CAMPAIGN_CONTEXT intentionally starts empty — SmartLead's version is keyed to real, live SmartLead
# campaign IDs (3249954, 3316611, 3442703, etc.) that only exist on SmartLead and never will here.
# The SpeakerAgent (3316611) and HVAC (3442703-3442706) hardcoded-template branches from the SmartLead
# daemon are dropped entirely for the same reason — those campaigns stay on SmartLead per the migration
# decision, so the dead-campaign-ID special-casing would never fire. Populate this dict once real
# Instantly campaigns launch, following the same pattern as auto_reply_daemon.py's CAMPAIGN_CONTEXT.
CAMPAIGN_CONTEXT = {}
FALLBACK_CONTEXT = f"Our original email was about AI-powered business automation services from {BUSINESS_NAME}."

def generate_reply(reply_body, lead_name, company_name, our_original_subject, campaign_id=None, sender_name=None):
    """Generate a reply using DeepSeek. Unchanged from auto_reply_daemon.py except CAMPAIGN_CONTEXT lookup."""
    context = CAMPAIGN_CONTEXT.get(str(campaign_id), FALLBACK_CONTEXT)

    booking_link = f"Include this link: {BOOKING_URL}" if BOOKING_URL else ""

    prompt = f"""You are the operator at {BUSINESS_NAME}, replying to a cold email response.

{context}

The lead replied with:
\"{reply_body[:500]}\"

Their name: {lead_name}
Company: {company_name}
Original subject: {our_original_subject}

Write a warm, human reply. Rules:
- First line: thank them for responding
- Reference something SPECIFIC from their reply
- If they said yes/interested: offer a 15-min call. {booking_link}
- If they referred someone: thank them, say you'll reach out
- 40-80 words max
- No emojis, no hype, no bullet points
- Sign off based on the campaign context
- Output ONLY the email body text, nothing else."""

    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 250,
        "temperature": 0.5,
    }).encode()

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=20, context=ctx)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"DeepSeek error: {e}")
        return None

# ─── Classifier ─────────────────────────────────────────────
# Unchanged from auto_reply_daemon.py — pure text classification, no platform dependency.
def classify(body_text, subject=""):
    body_lower = (body_text + " " + subject).lower()

    # OOO detection
    ooo_patterns = ['out of the office', 'out of office', 'i am out', "i'm out",
                    'i will be out', 'away from', 'maternity leave', 'annual leave',
                    'returning on', 'back on', 'returning in', 'vacation']
    if any(p in body_lower for p in ooo_patterns):
        return 'ooo'

    # Hostile
    hostile_patterns = ['stop', 'block you', 'do not contact', 'stop emailing',
                        'fuck', 'report you', 'reporting spam', 'mark as spam', 'lawsuit']
    if any(p in body_lower for p in hostile_patterns) and len(body_text) < 200:
        return 'hostile'

    # Unsubscribe
    unsub_patterns = ['unsubscribe', 'remove me', 'take me off', 'opt out',
                      'do not email', 'permanently']
    if any(p in body_lower for p in unsub_patterns):
        return 'unsubscribe'

    # Closed/bounce
    if any(p in body_lower for p in ['permanently closed', 'no longer at this address', 'no longer valid', 'no longer in use', 'address not found', 'message blocked',
                                      'undeliverable', 'mailbox full']):
        return 'dead'

    # One-word agreements (must check BEFORE generic positive patterns)
    cleaned = body_lower.strip().rstrip('.!?,;')
    one_word_agreements = ['sure', 'ok', 'yep', 'absolutely', 'definitely', 'indeed',
                           'yes', 'okay', 'sounds good', 'yeah', 'of course']
    if cleaned in one_word_agreements or any(cleaned == w for w in one_word_agreements):
        return 'positive_interested'

    # Negative - not interested (check BEFORE positive patterns to avoid false matches)
    negative_patterns = ['not interested', 'no thanks', 'no thx', 'no thank you',
                         'not a fit', 'don\'t need', 'we\'re good', 'we are good',
                         'not at this time', 'pass']
    if any(p in body_lower for p in negative_patterns):
        return 'negative_notfit'

    # Positive - interested
    interested = ['interested', 'tell me more', 'love to learn', 'set up', 'schedule',
                  'book a call', 'let\'s talk', 'would love', 'please send']
    if any(p in body_lower for p in interested):
        return 'positive_interested'

    # Referral
    referral = ['talk to', 'contact', 'reach out to', 'speak with', 'send all', 'new cfo',
                'new contact', 'try ']
    if any(p in body_lower for p in referral):
        return 'positive_referral'

    return 'neutral'

# ─── Action Handlers ────────────────────────────────────────
# Unchanged from auto_reply_daemon.py except draft dict fields (reply_to_uuid instead of
# campaign_id/stats_id) and the state key it writes into (hostile_senders/unsub_senders are shared
# in shape, but this is a SEPARATE state file — see instantly_reply_state.json, never auto_reply_state.json).
def handle_positive(lead, reply_body, history):
    """Generate a draft reply and output for operator approval. Does NOT auto-send."""
    lead_name = lead.get('from_name', '') or lead.get('lead_name', '') or lead.get('from_address_email', '')
    campaign_id = lead.get('campaign_id')

    our_msgs = [m for m in history if m.get('type') == 'SENT' or m.get('direction') == 'sent']
    our_subject = our_msgs[0].get('subject', 'Re:') if our_msgs else 'Re:'
    sender_name = our_msgs[0].get('from', '') if our_msgs else ''

    reply = generate_reply(reply_body, lead_name, "", our_subject, campaign_id, sender_name)
    if not reply:
        log(f"  Failed to generate draft for {lead_name}")
        return None

    log(f"  Draft generated for {lead_name}")
    draft = {
        "lead_name": lead_name.strip(),
        "lead_email": lead.get('from_email', ''),
        "campaign_id": campaign_id,
        "reply_to_uuid": lead.get('id', ''),
        "reply_snippet": reply_body[:150].replace('\n', ' ').strip(),
        "draft_reply": reply,
        "label": "interested",
    }
    print(f"__DRAFT__:{json.dumps(draft)}", flush=True)
    return draft

def handle_ooo(lead):
    log(f"  OOO - archiving")

def handle_unsub(lead):
    log(f"  Unsubscribe - processing")

def handle_hostile(lead, state):
    sender = lead.get('from_email', '')
    state['hostile_senders'].append(sender)
    log(f"  HOSTILE from {sender} - pausing lead")

def handle_dead(lead):
    log(f"  Dead lead - pausing")

# ─── Main Loop ──────────────────────────────────────────────
def main():
    once = '--once' in sys.argv
    counts = {"handled": 0, "positive": 0, "referral": 0, "ooo": 0,
              "unsub": 0, "hostile": 0, "dead": 0, "neutral": 0}
    drafts = []

    log("Instantly auto-reply daemon starting...")
    if BOOKING_URL:
        log(f"   Booking link: {BOOKING_URL}")
    log(f"   Business name: {BUSINESS_NAME}")
    log(f"   Poll interval: {POLL_INTERVAL}s")
    log(f"   Mode: {'once' if once else 'continuous'}")

    while True:
        try:
            state = load_state()
            save_state(state)  # persist unconditionally so the state file always exists after a run,
                                # even with 0 unread — matters for --once dry-runs and cron sanity checks
            unread = get_unread()

            if not unread:
                if once:
                    log("No unread replies. Exiting.")
                    print(f"__SUMMARY__:{json.dumps(counts)}", flush=True, file=sys.stderr)
                    break
                time.sleep(POLL_INTERVAL)
                continue

            log(f"\n{len(unread)} unread replies")

            for lead in unread:
                # Instantly threads on a single id (reply_to_uuid), not SmartLead's
                # (campaign_id, lead_id, email_stats_id) triple — this is the load-bearing
                # simplification from the migration plan. Field name 'id' is UNVERIFIED.
                email_id = lead.get('id', '')
                name = lead.get('from_name', '') or lead.get('from_address_email', '') or lead.get('from_email', '')

                # IDEMPOTENCY CHECK — simpler than SmartLead's timestamp-comparison hack
                # because Instantly's model gives each reply its own id up front (assumed;
                # confirm against a real payload). If that assumption is wrong and Instantly
                # actually needs thread-level history to find "the latest reply", port
                # SmartLead's our_replies_after pattern from auto_reply_daemon.py instead.
                if email_id and email_id in state.get('replied_message_ids', []):
                    log(f"  {name} -> SKIP (already processed)")
                    continue

                raw_body = lead.get('body', '') or lead.get('text', '')
                if isinstance(raw_body, dict):
                    raw_body = raw_body.get('text', '') or raw_body.get('html', '')
                body_text = re.sub(r'<[^>]+>', ' ', raw_body)
                body_text = re.sub(r'\s+', ' ', body_text).strip()
                body_text = html.unescape(body_text)

                if not body_text:
                    # Body wasn't inline on the unread listing — fall back to a thread fetch.
                    # get_messages()'s filter param is unverified; this path is untested.
                    history = get_messages(email_id)
                    replies = [m for m in history if m.get('type') == 'REPLY' or m.get('direction') == 'received']
                    if not replies:
                        continue
                    latest = replies[-1]
                    raw_body = latest.get('body', '') or latest.get('email_body', '')
                    body_text = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', raw_body)).strip())
                else:
                    history = [lead]

                label = classify(body_text, lead.get('subject', ''))

                log(f"  {name} -> {label}")
                counts["handled"] += 1

                if label == 'positive_interested':
                    counts["positive"] += 1
                    draft = handle_positive(lead, body_text, history)
                    if draft:
                        drafts.append(draft)
                elif label == 'positive_referral':
                    counts["referral"] += 1
                    draft = handle_positive(lead, body_text, history)
                    if draft:
                        draft['label'] = 'referral'
                        drafts.append(draft)
                elif label == 'ooo':
                    counts["ooo"] += 1
                    handle_ooo(lead)
                elif label == 'unsubscribe':
                    counts["unsub"] += 1
                    handle_unsub(lead)
                elif label == 'hostile':
                    counts["hostile"] += 1
                    handle_hostile(lead, state)
                elif label == 'dead':
                    counts["dead"] += 1
                    handle_dead(lead)
                else:
                    counts["neutral"] += 1

                if email_id:
                    state.setdefault('replied_message_ids', []).append(email_id)
                save_state(state)

                time.sleep(2)  # Rate limit

            if once:
                log("Batch complete. Exiting.")
                if drafts:
                    print(f"__DRAFTS_COUNT__:{len(drafts)}", flush=True)
                    with open(DRAFT_FILE, 'w') as f:
                        json.dump(drafts, f, indent=2)
                    log(f"  Drafts saved to {DRAFT_FILE}")
                print(f"__SUMMARY__:{json.dumps(counts)}", flush=True, file=sys.stderr)
                break

        except KeyboardInterrupt:
            log("Shutting down...")
            break
        except Exception as e:
            log(f"Error: {e}")
            if once:
                break
            time.sleep(10)

    log("Daemon stopped.")

if __name__ == "__main__":
    main()
