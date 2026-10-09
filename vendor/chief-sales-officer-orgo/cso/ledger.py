"""Local recovery journal. No network access and no external CRM mutation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

STAGES = {
    'sales': ['new', 'qualified', 'meeting_booked', 'discovery_complete', 'proposal', 'negotiation', 'won', 'lost'],
    'partner': ['identified', 'qualified', 'onboarding', 'activated', 'producing', 'dormant', 'closed'],
    'client': ['onboarding', 'active', 'expansion', 'referral_ready', 'closed'],
}
SOURCES = ['email_inbound', 'email_outbound', 'linkedin', 'calendar', 'calls', 'ai-go-to-market', 'revenue-partner']

def now():
    return datetime.now(timezone.utc).isoformat()

def stamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return dt.astimezone(timezone.utc).isoformat()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

class Ledger:
    def __init__(self, path):
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS events (
          source TEXT, event_id TEXT, fingerprint TEXT NOT NULL, observed_at TEXT NOT NULL,
          payload TEXT NOT NULL, PRIMARY KEY(source,event_id));
        CREATE TABLE IF NOT EXISTS opportunities (
          id TEXT PRIMARY KEY, person_id TEXT NOT NULL, pipeline TEXT NOT NULL,
          stage TEXT NOT NULL, owner TEXT NOT NULL, next_action TEXT NOT NULL,
          due_at TEXT NOT NULL, evidence TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assignments (
          id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
          executor TEXT NOT NULL, action TEXT NOT NULL, due_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued', receipt TEXT, fingerprint TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox (
          id TEXT PRIMARY KEY, destination TEXT NOT NULL, payload TEXT NOT NULL,
          fingerprint TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', receipt TEXT);
        CREATE TABLE IF NOT EXISTS sources (
          id TEXT PRIMARY KEY, checked_at TEXT NOT NULL, watermark TEXT,
          status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL);
        ''')

    def audit(self, action, payload):
        self.db.execute('INSERT INTO audit(at,action,payload) VALUES(?,?,?)', (now(), action, json.dumps(payload, sort_keys=True)))

    def ingest(self, event):
        for field in ['source', 'event_id', 'observed_at', 'person_id', 'evidence']:
            if not isinstance(event.get(field), str) or not event[field].strip():
                raise ValueError('Missing event field: ' + field)
        if event['source'] not in SOURCES:
            raise ValueError('Unknown source')
        stamp(event['observed_at'])
        fp = digest(event)
        old = self.db.execute('SELECT fingerprint FROM events WHERE source=? AND event_id=?', (event['source'], event['event_id'])).fetchone()
        if old:
            if old['fingerprint'] != fp:
                raise ValueError('Event identity reused with changed data; reconcile before retry')
            return {'status': 'duplicate'}
        with self.db:
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?)', (event['source'], event['event_id'], fp, stamp(event['observed_at']), json.dumps(event)))
            self.audit('event_ingested', {'source': event['source'], 'event_id': event['event_id']})
        return {'status': 'recorded', 'notice': 'No opportunity or external write implied'}

    def upsert_opportunity(self, record):
        for key in ['id', 'person_id', 'pipeline', 'stage', 'owner', 'next_action', 'due_at', 'evidence']:
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError('Missing opportunity field: ' + key)
        pipeline, stage = record['pipeline'], record['stage']
        if pipeline not in STAGES or stage not in STAGES[pipeline]:
            raise ValueError('Invalid pipeline stage')
        due = stamp(record['due_at'])
        evidence = record['evidence']
        # Evidence is a source:event_id reference; the person must match the source record.
        source, sep, event_id = evidence.partition(':')
        row = self.db.execute('SELECT payload FROM events WHERE source=? AND event_id=?', (source, event_id)).fetchone()
        if not sep or not row or json.loads(row['payload'])['person_id'] != record['person_id']:
            raise ValueError('Evidence must reference a recorded event for this person')
        event = json.loads(row['payload'])
        if event.get('stage_evidence') != stage or event.get('pipeline') != pipeline:
            raise ValueError('Source does not support this pipeline stage')
        old = self.db.execute('SELECT * FROM opportunities WHERE id=?', (record['id'],)).fetchone()
        if old and (old['person_id'] != record['person_id'] or old['pipeline'] != pipeline):
            raise ValueError('Opportunity identity cannot change person or pipeline')
        if pipeline == 'sales' and stage == 'won' and event.get('outcome') not in ['signed', 'paid']:
            raise ValueError('Won requires signed or paid evidence')
        with self.db:
            self.db.execute('''INSERT INTO opportunities VALUES(?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET stage=excluded.stage,owner=excluded.owner,
              next_action=excluded.next_action,due_at=excluded.due_at,evidence=excluded.evidence,updated_at=excluded.updated_at''',
              (record['id'], record['person_id'], pipeline, stage, record['owner'], record['next_action'], due, evidence, now()))
            self.audit('opportunity_updated', record)
        return {'status': 'local', 'id': record['id']}

    def assign(self, record):
        for key in ['id', 'opportunity_id', 'executor', 'action', 'due_at']:
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError('Missing assignment field: ' + key)
        fp = digest(record)
        old = self.db.execute('SELECT fingerprint FROM assignments WHERE id=?', (record['id'],)).fetchone()
        if old:
            if old['fingerprint'] != fp:
                raise ValueError('Assignment ID reused with changed data')
            return {'status': 'duplicate'}
        with self.db:
            self.db.execute('INSERT INTO assignments(id,opportunity_id,executor,action,due_at,fingerprint) VALUES(?,?,?,?,?,?)',
                            (record['id'], record['opportunity_id'], record['executor'], record['action'], stamp(record['due_at']), fp))
            self.audit('assignment_queued', record)
        return {'status': 'queued', 'notice': 'Requires executor acceptance; not dispatched externally'}

    def enqueue(self, record):
        if not all(isinstance(record.get(k), str) and record[k].strip() for k in ['id', 'destination']):
            raise ValueError('Outbox needs a durable ID and destination')
        if record['destination'] not in ['crm', 'tasks', 'slack', 'proof', 'transcription'] or not isinstance(record.get('payload'), dict):
            raise ValueError('Invalid adapter request')
        fp = digest(record)
        old = self.db.execute('SELECT fingerprint FROM outbox WHERE id=?', (record['id'],)).fetchone()
        if old:
            if old['fingerprint'] != fp:
                raise ValueError('Outbox ID reused with changed data')
            return {'status': 'duplicate'}
        with self.db:
            self.db.execute('INSERT INTO outbox(id,destination,payload,fingerprint) VALUES(?,?,?,?)', (record['id'], record['destination'], json.dumps(record['payload']), fp))
            self.audit('adapter_request_queued', record)
        return {'status': 'queued'}

    def acknowledge(self, record):
        if record.get('table') not in ['outbox', 'assignments'] or record.get('status') not in ['confirmed', 'ambiguous']:
            raise ValueError('Invalid acknowledgment')
        if not isinstance(record.get('receipt'), str) or not record['receipt'].strip():
            raise ValueError('Authoritative receipt or reconciliation evidence required')
        table = record['table']
        row = self.db.execute(f'SELECT status,receipt FROM {table} WHERE id=?', (record.get('id'),)).fetchone()
        if not row:
            raise ValueError('Unknown request')
        if row['status'] == 'confirmed':
            if record['status'] != 'confirmed' or row['receipt'] != record['receipt']:
                raise ValueError('Confirmed receipt cannot be replaced')
            return {'status': 'duplicate'}
        with self.db:
            self.db.execute(f'UPDATE {table} SET status=?,receipt=? WHERE id=?', (record['status'], record['receipt'], record['id']))
            self.audit('receipt_recorded', record)
        return {'status': record['status']}

    def source_check(self, record):
        if record.get('id') not in SOURCES or record.get('status') not in ['connected', 'unavailable']:
            raise ValueError('Invalid source check')
        checked = stamp(record['checked_at'])
        if record['status'] == 'connected' and not record.get('watermark'):
            raise ValueError('Connected source needs a reconciled watermark')
        with self.db:
            self.db.execute('INSERT INTO sources VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET checked_at=excluded.checked_at,watermark=excluded.watermark,status=excluded.status',
                            (record['id'], checked, record.get('watermark'), record['status']))
            self.audit('source_checked', record)
        return {'status': 'recorded'}

    def review(self, at=None):
        at = stamp(at or now())
        rows = lambda query, args=(): [dict(r) for r in self.db.execute(query, args)]
        sources = {r['id']: dict(r) for r in self.db.execute('SELECT * FROM sources')}
        gaps = []
        for source in SOURCES:
            s = sources.get(source)
            if not s or s['status'] != 'connected':
                gaps.append({'source': source, 'reason': 'unverified or unavailable'})
            elif (datetime.fromisoformat(at) - datetime.fromisoformat(s['checked_at'])).total_seconds() > 86400:
                gaps.append({'source': source, 'reason': 'stale, last checked ' + s['checked_at']})
        return {'as_of': at, 'source_gaps': gaps,
                'overdue_opportunities': rows("SELECT * FROM opportunities WHERE due_at<=? AND stage NOT IN ('won','lost','closed') ORDER BY due_at", (at,)),
                'due_assignments': rows("SELECT * FROM assignments WHERE due_at<=? AND status!='confirmed' ORDER BY due_at", (at,)),
                'pending_adapter_requests': rows("SELECT id,destination,status,receipt FROM outbox WHERE status!='confirmed'"),
                'notice': 'Local journal only. Queued is not executed; unverified sources are unknown.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='~/.hermes/cso/pipeline.db')
    parser.add_argument('command', choices=['ingest', 'opportunity', 'assign', 'enqueue', 'acknowledge', 'source-check', 'review'])
    parser.add_argument('--file', help='Private normalized JSON input, never a credential file')
    args = parser.parse_args()
    ledger = Ledger(args.db)
    try:
        if args.command == 'review':
            result = ledger.review()
        else:
            if not args.file:
                parser.error('--file is required')
            record = json.loads(Path(args.file).read_text())
            handler = {'ingest': ledger.ingest, 'opportunity': ledger.upsert_opportunity, 'assign': ledger.assign, 'enqueue': ledger.enqueue, 'acknowledge': ledger.acknowledge, 'source-check': ledger.source_check}[args.command]
            result = handler(record)
        print(json.dumps(result, indent=2))
    finally:
        ledger.db.close()

if __name__ == '__main__':
    main()
