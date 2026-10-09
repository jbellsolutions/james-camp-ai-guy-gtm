"""rel.sqlite3: the relationship index and context graph (owner: trp). Rebuildable from the vault except the
registers, suppression and audit, which are append-only and backed up nightly."""
from . import append_only, fts5_available

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('person','partner','partnership')),
  display TEXT NOT NULL, fields TEXT NOT NULL DEFAULT '{}', note_path TEXT, digest TEXT,
  internal INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS entities_kind ON entities(kind);
CREATE TABLE IF NOT EXISTS identities (
  type TEXT NOT NULL, value_norm TEXT NOT NULL, entity_id TEXT NOT NULL REFERENCES entities(id),
  source TEXT, added_at TEXT NOT NULL, PRIMARY KEY (type, value_norm));
CREATE INDEX IF NOT EXISTS identities_entity ON identities(entity_id);
CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES entities(id), slot TEXT NOT NULL,
  value TEXT NOT NULL, value_key TEXT NOT NULL, source TEXT NOT NULL, source_ref TEXT, by TEXT NOT NULL,
  recorded_at TEXT NOT NULL, recorded_by TEXT, confidence TEXT NOT NULL DEFAULT 'medium',
  volunteered INTEGER NOT NULL DEFAULT 0, removed_at TEXT, UNIQUE (entity_id, slot, value_key));
CREATE TABLE IF NOT EXISTS edges (
  id INTEGER PRIMARY KEY, src TEXT NOT NULL, type TEXT NOT NULL, dst TEXT NOT NULL, props TEXT NOT NULL DEFAULT '{}',
  source TEXT, source_ref TEXT, confidence TEXT NOT NULL DEFAULT 'high', since TEXT NOT NULL, until TEXT,
  UNIQUE (src, type, dst));
CREATE INDEX IF NOT EXISTS edges_dst ON edges(dst);
CREATE TABLE IF NOT EXISTS hubs (kind TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (kind, value));
CREATE TABLE IF NOT EXISTS interactions (
  id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, partnership_id TEXT, kind TEXT NOT NULL, channel TEXT,
  direction TEXT CHECK (direction IN ('in','out','internal')), provider TEXT, provider_msg_id TEXT, at TEXT NOT NULL,
  summary TEXT, body_hash TEXT, template_version TEXT, action_id TEXT, UNIQUE (provider, provider_msg_id));
CREATE INDEX IF NOT EXISTS interactions_entity ON interactions(entity_id, at);
CREATE TABLE IF NOT EXISTS timeline (id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, at TEXT NOT NULL, line TEXT NOT NULL,
  ref TEXT, UNIQUE (entity_id, ref));
CREATE INDEX IF NOT EXISTS timeline_entity ON timeline(entity_id, id);
CREATE TABLE IF NOT EXISTS open_loops (
  id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, partnership_id TEXT, owner TEXT NOT NULL CHECK (owner IN ('us','them')),
  text TEXT NOT NULL, due TEXT, status TEXT NOT NULL DEFAULT 'open', source_ref TEXT, created_at TEXT NOT NULL,
  closed_at TEXT, UNIQUE (entity_id, text, source_ref));
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, entity_id TEXT, title TEXT NOT NULL, detail TEXT, urgent INTEGER NOT NULL DEFAULT 0,
  assignee TEXT, status TEXT NOT NULL DEFAULT 'open', ref TEXT UNIQUE, created_at TEXT NOT NULL, closed_at TEXT);
CREATE TABLE IF NOT EXISTS holds (
  id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, kind TEXT NOT NULL, reason TEXT, ref TEXT, created_at TEXT NOT NULL,
  released_at TEXT, released_by TEXT, UNIQUE (entity_id, kind, ref));
CREATE TABLE IF NOT EXISTS suppression_local (
  type TEXT NOT NULL, value_norm TEXT NOT NULL, channel TEXT NOT NULL, reason TEXT NOT NULL, source TEXT,
  created_at TEXT NOT NULL, PRIMARY KEY (type, value_norm, channel));
CREATE TABLE IF NOT EXISTS consent (
  entity_id TEXT NOT NULL, channel TEXT NOT NULL, basis TEXT NOT NULL, source TEXT NOT NULL, at TEXT NOT NULL,
  PRIMARY KEY (entity_id, channel));
CREATE TABLE IF NOT EXISTS processed_inbound (provider TEXT NOT NULL, provider_msg_id TEXT NOT NULL, entity_id TEXT,
  processed_at TEXT NOT NULL, PRIMARY KEY (provider, provider_msg_id));
CREATE TABLE IF NOT EXISTS inbound (
  id INTEGER PRIMARY KEY, provider TEXT NOT NULL, last_msg_id TEXT NOT NULL, msg_ids TEXT NOT NULL, entity_id TEXT,
  partnership_id TEXT, channel TEXT NOT NULL, address TEXT NOT NULL, at TEXT NOT NULL, floor_intent TEXT NOT NULL,
  intent TEXT NOT NULL, matched TEXT, summary TEXT, status TEXT NOT NULL DEFAULT 'pending', action_id TEXT, note TEXT,
  created_at TEXT NOT NULL, UNIQUE (provider, last_msg_id));
CREATE INDEX IF NOT EXISTS inbound_status ON inbound(status, at);
CREATE TABLE IF NOT EXISTS calls (
  id TEXT PRIMARY KEY, source TEXT NOT NULL, external_id TEXT NOT NULL, started_at TEXT NOT NULL, duration INTEGER,
  note_path TEXT, person_id TEXT, partnership_id TEXT, status TEXT NOT NULL DEFAULT 'rules', transcript TEXT,
  created_at TEXT NOT NULL, reviewed_at TEXT, UNIQUE (source, external_id));
CREATE TABLE IF NOT EXISTS spool_seen (dir TEXT NOT NULL, name TEXT NOT NULL, at TEXT NOT NULL, outcome TEXT,
  PRIMARY KEY (dir, name));
CREATE TABLE IF NOT EXISTS actions (
  action_id TEXT PRIMARY KEY, kind TEXT NOT NULL, employee TEXT, state TEXT NOT NULL, payload_hash TEXT, bundle_path TEXT,
  review_path TEXT, prepared_at TEXT NOT NULL, expires_at TEXT NOT NULL, decided_at TEXT, detail TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS action_messages (
  action_id TEXT NOT NULL, n INTEGER NOT NULL, entity_id TEXT NOT NULL, partnership_id TEXT, channel TEXT NOT NULL,
  address TEXT NOT NULL, subject TEXT, body TEXT NOT NULL, body_hash TEXT NOT NULL, hook TEXT, template TEXT, arm TEXT,
  reply_to TEXT, context_digest TEXT, state TEXT NOT NULL DEFAULT 'prepared', first_touch_flag INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (action_id, n));
CREATE TABLE IF NOT EXISTS reservations (entity_id TEXT PRIMARY KEY, action_id TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, partnership_id TEXT, channel TEXT NOT NULL, subject TEXT, body TEXT NOT NULL,
  context_digest TEXT NOT NULL, lint TEXT NOT NULL, employee TEXT, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft');
CREATE TABLE IF NOT EXISTS eligibility (
  program TEXT NOT NULL, entity_id TEXT NOT NULL, rule TEXT NOT NULL, as_of TEXT NOT NULL, basis TEXT NOT NULL,
  snapshot_hash TEXT NOT NULL, PRIMARY KEY (program, entity_id));
CREATE TABLE IF NOT EXISTS engagement (
  id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, partnership_id TEXT, msg_ref TEXT NOT NULL, at TEXT NOT NULL,
  channel TEXT, tier_at TEXT, UNIQUE (entity_id));
CREATE TABLE IF NOT EXISTS holdout (entity_id TEXT PRIMARY KEY, wave TEXT NOT NULL, segment TEXT, assigned_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS arms (entity_id TEXT PRIMARY KEY, wave TEXT NOT NULL, arm TEXT NOT NULL, assigned_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cursors (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, at TEXT NOT NULL, model TEXT, purpose TEXT, tokens_in INTEGER,
  tokens_out INTEGER, cost REAL);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  ref TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS applied_refs (entity_id TEXT NOT NULL, source_ref TEXT NOT NULL, by TEXT NOT NULL,
  at TEXT NOT NULL, PRIMARY KEY (entity_id, source_ref, by));
CREATE TABLE IF NOT EXISTS refused (id INTEGER PRIMARY KEY, at TEXT NOT NULL, entity_id TEXT, slot TEXT, reason TEXT NOT NULL,
  source_ref TEXT);
""" + append_only("audit") + append_only("timeline") + append_only("engagement") + append_only("eligibility") + """
CREATE TRIGGER IF NOT EXISTS suppression_local_no_delete BEFORE DELETE ON suppression_local
  BEGIN SELECT RAISE(ABORT, 'suppression can only be added'); END;
CREATE TRIGGER IF NOT EXISTS holdout_no_delete BEFORE DELETE ON holdout BEGIN SELECT RAISE(ABORT, 'holdout is frozen'); END;
""" + ("""
CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(entity_id UNINDEXED, kind UNINDEXED, display, body);
""" if fts5_available() else """
CREATE TABLE IF NOT EXISTS search (entity_id TEXT, kind TEXT, display TEXT, body TEXT);
""")
