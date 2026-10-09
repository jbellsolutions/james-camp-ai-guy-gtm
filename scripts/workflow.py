#!/usr/bin/env python3
"""Durable reply ledger; no provider calls. Acknowledgements require receipts."""
import argparse,json,re,sqlite3
from pathlib import Path
SCHEMA='''CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, client TEXT, provider TEXT, account TEXT, event_key TEXT, envelope TEXT, UNIQUE(client,provider,account,event_key));
CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, event_id INTEGER, owner TEXT, action TEXT, priority INTEGER, status TEXT DEFAULT 'pending', receipt TEXT, UNIQUE(event_id,owner,action));
CREATE TABLE IF NOT EXISTS suppression (client TEXT, contact TEXT, reason TEXT, UNIQUE(client,contact));'''
REQUIRED=['client','provider','account','event_id','channel','contact','thread_id','occurred_at','kind','text']
def connect(db):
    db=Path(db)
    if not db.parent.exists():db.parent.mkdir(parents=True);db.parent.chmod(0o700)
    c=sqlite3.connect(db);c.row_factory=sqlite3.Row;c.executescript(SCHEMA);db.chmod(0o600);return c

def validate(e):
    if not isinstance(e,dict):raise ValueError('Envelope must be an object')
    for k in REQUIRED:
        if not isinstance(e.get(k),str) or (not e[k].strip() and k!='text'):raise ValueError('Missing/invalid '+k)
    if e['client']!='james-camp':raise ValueError('Wrong client')
    if e['channel'] not in ['email','sms']:raise ValueError('Unsupported channel')
    if e['kind'] not in ['reply','unsubscribe','complaint','wrong_number']:raise ValueError('Unsupported kind')
    if e['channel']=='email' and not e.get('campaign_id'):raise ValueError('Email campaign ID required')

def ingest(c,e):
    validate(e);kind=e['kind'];text=e['text'].strip().lower()
    if re.search(r'\b(unsubscribe|stop texting|stop emailing|remove me|do not contact|wrong number)\b',text) or text in ['stop','cancel','end','quit']:
        kind='wrong_number' if 'wrong number' in text else 'unsubscribe'
    blocked=kind in ['unsubscribe','complaint','wrong_number']
    with c:
        cur=c.execute('INSERT OR IGNORE INTO events(client,provider,account,event_key,envelope) VALUES(?,?,?,?,?)',(e['client'],e['provider'],e['account'],e['event_id'],json.dumps(e)))
        if not cur.rowcount:return {'duplicate':True}
        eid=cur.lastrowid;work=[]
        if e['channel']=='email':work.append(('gtm-sequencer','stop_sequence',0))
        if blocked:
            c.execute('INSERT OR IGNORE INTO suppression VALUES(?,?,?)',(e['client'],e['contact'].strip().lower(),kind))
            c.execute('UPDATE tasks SET status="cancelled" WHERE action="triage_reply" AND status IN ("pending","held","claimed") AND event_id IN (SELECT id FROM events WHERE client=? AND json_extract(envelope,"$.contact")=? )',(e['client'],e['contact']))
            work.extend([('gtm-sequencer' if e['channel']=='email' else 'crm-agent-4','suppress_provider',0),('crm-agent-4','suppress_crm',0)])
        else:
            suppressed=c.execute('SELECT 1 FROM suppression WHERE client=? AND contact=?',(e['client'],e['contact'].strip().lower())).fetchone()
            if not suppressed:work.append(('gtm-replies' if e['channel']=='email' else 'relationship-manager','triage_reply',1))
        work.append(('crm-agent-4','context_handoff',2))
        for owner,action,priority in work:c.execute('INSERT OR IGNORE INTO tasks(event_id,owner,action,priority) VALUES(?,?,?,?)',(eid,owner,action,priority))
    return {'event_id':eid,'blocked':blocked,'tasks':len(work)}

def tasks(c,owner):
    return [dict(r) for r in c.execute('SELECT tasks.*, events.envelope FROM tasks JOIN events ON events.id=tasks.event_id WHERE owner=? AND status="pending" AND (priority=0 OR NOT EXISTS (SELECT 1 FROM tasks blockers WHERE blockers.event_id=tasks.event_id AND blockers.priority=0 AND blockers.status!="done")) ORDER BY priority,tasks.id',(owner,))]


def claim(c,owner):
    # Do not expire/retry a claim automatically: an interrupted external write may have succeeded.
    c.execute('BEGIN IMMEDIATE')
    try:
        available=tasks(c,owner)
        if not available:c.commit();return None
        item=available[0]
        c.execute('UPDATE tasks SET status="claimed" WHERE id=? AND status="pending"',(item['id'],))
        c.commit();item['status']='claimed';return item
    except Exception:
        c.rollback();raise

def ack(c,id,receipt):
    if not isinstance(receipt,dict) or not receipt.get('external_id') or receipt.get('status')!='confirmed':raise ValueError('Confirmed external receipt required')
    with c:
        cur=c.execute('UPDATE tasks SET status="done",receipt=? WHERE id=? AND status IN ("pending","claimed")',(json.dumps(receipt),id))
        if not cur.rowcount:raise ValueError('Task missing, held or already acknowledged')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);sub=p.add_subparsers(dest='cmd',required=True)
    x=sub.add_parser('ingest');x.add_argument('event',type=Path)
    x=sub.add_parser('tasks');x.add_argument('--owner',required=True)
    x=sub.add_parser('claim');x.add_argument('--owner',required=True)
    x=sub.add_parser('ack');x.add_argument('id',type=int);x.add_argument('receipt',type=Path)
    for command in ['hold','retry']:
        x=sub.add_parser(command);x.add_argument('id',type=int)
    a=p.parse_args()
    if (a.db.parent/'EXTERNAL_WRITES_STOPPED').exists() and a.cmd in ['tasks','claim','retry']:raise SystemExit('Work stopped')
    c=connect(a.db)
    if a.cmd=='ingest':print(json.dumps(ingest(c,json.loads(a.event.read_text()))))
    elif a.cmd=='tasks':print(json.dumps(tasks(c,a.owner)))
    elif a.cmd=='claim':print(json.dumps(claim(c,a.owner)))
    elif a.cmd=='ack':ack(c,a.id,json.loads(a.receipt.read_text()));print('acknowledged')
    else:
        with c:
            if a.cmd=='hold':c.execute('UPDATE tasks SET status="held" WHERE id=? AND status IN ("pending","claimed")',(a.id,))
            else:c.execute('UPDATE tasks SET status="pending" WHERE id=? AND status="held"',(a.id,))
        print(a.cmd)
