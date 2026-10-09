"""approvals.sqlite3 (owner: relapprove). What was shown to the owner, what they decided, and the signature."""
from . import append_only

SCHEMA = """
CREATE TABLE IF NOT EXISTS bundles_seen (
  action_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL,
  problems TEXT NOT NULL DEFAULT '[]', shown_at TEXT NOT NULL, slack_channel TEXT, slack_ts TEXT,
  edits TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS decisions (
  approval_id TEXT PRIMARY KEY, action_id TEXT NOT NULL UNIQUE, decision TEXT NOT NULL, payload_hash TEXT NOT NULL,
  exclusions TEXT NOT NULL, edits TEXT NOT NULL, approver TEXT NOT NULL, approver_name TEXT, via TEXT NOT NULL,
  decided_at TEXT NOT NULL, expires_at TEXT NOT NULL, hmac TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS holds_released (
  approval_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, kind TEXT NOT NULL, approver TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS slack_events_seen (event_id TEXT PRIMARY KEY, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alerts_seen (name TEXT PRIMARY KEY, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  ref TEXT, detail TEXT);
""" + append_only("audit") + append_only("decisions")
