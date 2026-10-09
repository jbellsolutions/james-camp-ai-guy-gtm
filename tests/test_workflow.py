import json,tempfile,unittest,sys,threading,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import workflow,intake
from http.server import HTTPServer
class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/'events.sqlite';self.c=workflow.connect(self.db)
  self.e={'client':'james-camp','provider':'instantly','account':'test','event_id':'m1','channel':'email','contact':'alex@example.com','thread_id':'t1','campaign_id':'c1','occurred_at':'2026-10-09T12:00:00Z','kind':'reply','text':'How does this work?'}
 def tearDown(self):self.c.close();self.temp.cleanup()
 def test_replay_and_dependencies(self):
  workflow.ingest(self.c,self.e);self.assertTrue(workflow.ingest(self.c,self.e)['duplicate'])
  stops=workflow.tasks(self.c,'gtm-sequencer');self.assertEqual(len(stops),1)
  self.assertEqual(workflow.tasks(self.c,'gtm-replies'),[]);self.assertEqual(workflow.tasks(self.c,'crm-agent-4'),[])
  workflow.ack(self.c,stops[0]['id'],{'status':'confirmed','external_id':'stop-receipt'})
  self.assertEqual(len(workflow.tasks(self.c,'gtm-replies')),1);self.assertEqual(len(workflow.tasks(self.c,'crm-agent-4')),1)
 def test_optout_cancels_old_and_future_triage(self):
  workflow.ingest(self.c,self.e);self.assertTrue(workflow.ingest(self.c,dict(self.e,event_id='m2',text='Please remove me'))['blocked'])
  self.assertEqual(self.c.execute('SELECT status FROM tasks WHERE action="triage_reply"').fetchone()[0],'cancelled')
  workflow.ingest(self.c,dict(self.e,event_id='m3',text='Thanks'))
  self.assertEqual(self.c.execute('SELECT count(*) FROM tasks WHERE action="triage_reply" AND status="pending"').fetchone()[0],0)
 def test_sms_stop_wrong_number(self):
  for i,text in enumerate(['STOP','wrong number']):workflow.ingest(self.c,dict(self.e,event_id=str(i),channel='sms',text=text,contact='+1202555010'+str(i)))
  self.assertEqual(self.c.execute('SELECT count(*) FROM suppression').fetchone()[0],2)
  self.assertEqual(self.c.execute('SELECT count(*) FROM tasks WHERE action="triage_reply"').fetchone()[0],0)
 def test_receipt_and_unknown_hold(self):
  workflow.ingest(self.c,self.e);id=workflow.tasks(self.c,'gtm-sequencer')[0]['id']
  with self.assertRaises(ValueError):workflow.ack(self.c,id,{'status':'draft'})
  self.c.execute('UPDATE tasks SET status="held" WHERE id=?',(id,));self.c.commit()
  with self.assertRaises(ValueError):workflow.ack(self.c,id,{'status':'confirmed','external_id':'x'})
  self.assertEqual(workflow.tasks(self.c,'gtm-replies'),[])
 def test_other_client_rejected(self):
  with self.assertRaises(ValueError):workflow.ingest(self.c,dict(self.e,client='other'))
  self.assertEqual(self.c.execute('SELECT count(*) FROM events').fetchone()[0],0)
 def test_http_auth_and_replay(self):
  token='x'*32;server=HTTPServer(('127.0.0.1',0),intake.handler(self.db,token));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url='http://127.0.0.1:'+str(server.server_port)+'/events'
  def post(auth):return json.load(urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(self.e).encode(),headers={'Authorization':auth,'Content-Type':'application/json'})))
  try:
   with self.assertRaises(urllib.error.HTTPError) as error:post('Bearer wrong')
   self.assertEqual(error.exception.code,401);error.exception.close();self.assertFalse(post('Bearer '+token).get('duplicate',False));self.assertTrue(post('Bearer '+token)['duplicate'])
  finally:server.shutdown();server.server_close();thread.join()

 def test_atomic_claim_prevents_two_workers(self):
  workflow.ingest(self.c,self.e)
  first=workflow.claim(self.c,'gtm-sequencer');self.assertIsNotNone(first)
  other=workflow.connect(self.db)
  try:self.assertIsNone(workflow.claim(other,'gtm-sequencer'))
  finally:other.close()
  workflow.ack(self.c,first['id'],{'status':'confirmed','external_id':'actual-provider-receipt'})
  self.assertIsNotNone(workflow.claim(self.c,'gtm-replies'))

 def test_sms_reply_routes_to_customer_conversion(self):
  workflow.ingest(self.c,dict(self.e,channel='sms',contact='+12025550100'))
  self.assertEqual(len(workflow.tasks(self.c,'conversion-specialist')),1)
  self.assertEqual(workflow.tasks(self.c,'affiliate-manager'),[])
  self.assertEqual(workflow.tasks(self.c,'relationship-manager'),[])
