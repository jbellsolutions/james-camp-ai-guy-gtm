"""sends.sqlite3 (owner: relsend). Approved actions, the outbox, and every per-recipient guard the sender keeps."""
from . import append_only

SCHEMA = """
CREATE TABLE IF NOT EXISTS approved_actions (
  action_id TEXT PRIMARY KEY, approval_id TEXT NOT NULL UNIQUE, payload_hash TEXT NOT NULL, approver TEXT NOT NULL,
  decided_at TEXT NOT NULL, expires_at TEXT NOT NULL, prepared_at TEXT, received_at TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals_seen (file TEXT PRIMARY KEY, approval_id TEXT, outcome TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (
  row_id INTEGER PRIMARY KEY, action_id TEXT NOT NULL, n INTEGER NOT NULL, person_id TEXT, partnership_id TEXT,
  channel TEXT NOT NULL, address TEXT NOT NULL, subject TEXT, body TEXT NOT NULL, final_body TEXT NOT NULL,
  first_touch INTEGER NOT NULL, consent_basis TEXT, reply_to TEXT, timezone TEXT,
  state TEXT NOT NULL CHECK (state IN ('queued','blocked','sending','sent','failed','unknown','skipped','expired')),
  provider TEXT, provider_msg_id TEXT, reason TEXT, attempts INTEGER NOT NULL DEFAULT 0, next_try_at TEXT,
  updated_at TEXT NOT NULL, UNIQUE (action_id, n));
CREATE TABLE IF NOT EXISTS first_touch (key TEXT PRIMARY KEY, row_id INTEGER NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS touches (id INTEGER PRIMARY KEY, person_key TEXT NOT NULL, address TEXT NOT NULL, channel TEXT,
  at TEXT NOT NULL, row_id INTEGER, source TEXT NOT NULL DEFAULT 'relsend');
CREATE INDEX IF NOT EXISTS touches_person ON touches(person_key, at);
CREATE TABLE IF NOT EXISTS suppression (type TEXT NOT NULL, value TEXT NOT NULL, channel TEXT NOT NULL, reason TEXT NOT NULL,
  source TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (type, value, channel));
CREATE TABLE IF NOT EXISTS withdrawn (action_id TEXT PRIMARY KEY, at TEXT NOT NULL, reason TEXT);
CREATE TABLE IF NOT EXISTS spool_cursor (dir TEXT NOT NULL, name TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (dir, name));
CREATE TABLE IF NOT EXISTS inbox_watermark (provider TEXT NOT NULL, conversation_id TEXT NOT NULL, last_inbound_id TEXT,
  last_inbound_at TEXT, PRIMARY KEY (provider, conversation_id));
CREATE TABLE IF NOT EXISTS inbound_seen (provider TEXT NOT NULL, msg_id TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (provider, msg_id));
CREATE TABLE IF NOT EXISTS latest_inbound (address TEXT PRIMARY KEY, msg_id TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS delivery (row_id INTEGER NOT NULL, status TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (row_id, status));
CREATE TABLE IF NOT EXISTS limiter (channel TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS contract_runs (id INTEGER PRIMARY KEY, channel TEXT NOT NULL, kind TEXT NOT NULL, ok INTEGER NOT NULL,
  at TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS dry_sends (row_id INTEGER PRIMARY KEY, at TEXT NOT NULL, channel TEXT, address TEXT, final_body TEXT);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  ref TEXT, detail TEXT);
CREATE TRIGGER IF NOT EXISTS suppression_no_delete BEFORE DELETE ON suppression BEGIN SELECT RAISE(ABORT, 'suppression can only be added'); END;
CREATE TRIGGER IF NOT EXISTS first_touch_no_delete BEFORE DELETE ON first_touch BEGIN SELECT RAISE(ABORT, 'first touches are permanent'); END;
CREATE TRIGGER IF NOT EXISTS outbox_no_resend BEFORE UPDATE OF state ON outbox
  WHEN OLD.state IN ('sent','unknown') AND NEW.state != OLD.state
  BEGIN SELECT RAISE(ABORT, 'a sent or unknown message is never re-sent'); END;
""" + append_only("audit") + append_only("contract_runs")
