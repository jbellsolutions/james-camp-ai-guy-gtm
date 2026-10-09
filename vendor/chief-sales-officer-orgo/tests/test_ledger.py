import importlib.util
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ledger',ROOT/'cso/ledger.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.l=mod.Ledger(Path(self.temp.name)/'journal.db')
 def tearDown(self):self.l.db.close();self.temp.cleanup()
 def event(self,**kw):return dict(source='calendar',event_id='booking-1',observed_at='2026-10-08T12:00:00Z',person_id='p1',evidence='booking URL',pipeline='sales',stage_evidence='meeting_booked',**kw)
 def opp(self,**kw):
  r=dict(id='o1',person_id='p1',pipeline='sales',stage='meeting_booked',owner='closer',next_action='attend discovery',due_at='2026-10-09T12:00:00Z',evidence='calendar:booking-1');r.update(kw);return r
 def test_event_replay_and_conflict(self):
  e=self.event();self.l.ingest(e);self.assertEqual(self.l.ingest(e)['status'],'duplicate')
  with self.assertRaises(ValueError):self.l.ingest(dict(e,evidence='changed'))
 def test_stage_evidence_and_identity(self):
  self.l.ingest(self.event());self.l.upsert_opportunity(self.opp())
  for changes in [dict(stage='won'),dict(stage='discovery_complete'),dict(person_id='other'),dict(pipeline='partner')]:
   with self.assertRaises(ValueError):self.l.upsert_opportunity(self.opp(**changes))
 def test_won_needs_outcome(self):
  e=self.event();e.update(stage_evidence='won');self.l.ingest(e)
  with self.assertRaises(ValueError):self.l.upsert_opportunity(self.opp(stage='won'))
 def test_assignments_due_and_receipts(self):
  self.l.ingest(self.event());self.l.upsert_opportunity(self.opp())
  a=dict(id='a1',opportunity_id='o1',executor='Revenue Partner',action='prepare call brief',due_at='2026-10-09T08:00:00Z')
  self.l.assign(a);self.assertEqual(self.l.assign(a)['status'],'duplicate')
  self.assertEqual(len(self.l.review('2026-10-10T00:00:00Z')['due_assignments']),1)
  self.l.acknowledge(dict(table='assignments',id='a1',status='confirmed',receipt='executor readback'))
  self.assertEqual(len(self.l.review('2026-10-10T00:00:00Z')['due_assignments']),0)
 def test_ambiguous_write_blocks_completion(self):
  r=dict(id='crm-1',destination='crm',payload={'deal':'o1'});self.l.enqueue(r)
  self.l.acknowledge(dict(table='outbox',id='crm-1',status='ambiguous',receipt='timeout after request'))
  self.assertEqual(self.l.review()['pending_adapter_requests'][0]['status'],'ambiguous')
  with self.assertRaises(ValueError):self.l.enqueue(dict(r,payload={'deal':'o2'}))
 def test_disconnected_is_unknown_and_stale_is_gap(self):
  self.assertEqual(len(self.l.review()['source_gaps']),7)
  self.l.source_check(dict(id='calendar',status='connected',watermark='cursor-1',checked_at='2026-10-08T00:00:00Z'))
  self.assertEqual(len(self.l.review('2026-10-08T12:00:00Z')['source_gaps']),6)
  self.assertEqual(len(self.l.review('2026-10-10T12:00:00Z')['source_gaps']),7)
 def test_timezone_normalization(self):
  self.l.ingest(self.event());self.l.upsert_opportunity(self.opp(due_at='2026-10-09T08:00:00-04:00'))
  self.assertEqual(len(self.l.review('2026-10-09T12:00:00Z')['overdue_opportunities']),1)
  with self.assertRaises(ValueError):mod.stamp('2026-10-09T08:00:00')
if __name__=='__main__':unittest.main()
