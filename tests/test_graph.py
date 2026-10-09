import json,os,subprocess,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
class GraphTests(unittest.TestCase):
 def test_sample_cards_context_and_safe_mcp_tools(self):
  with tempfile.TemporaryDirectory() as td:
   env=dict(os.environ,GTM_STATE_ROOT=td)
   def run(*args):
    p=subprocess.run(['bash',str(R/'scripts/relationship.sh'),*args],env=env,text=True,capture_output=True)
    self.assertEqual(p.returncode,0,p.stderr);return p.stdout
   run('init');counts=json.loads(run('import','apply','csv',str(R/'vendor/affiliate-manager-agent/examples/relationship'),'--client','Synthetic James Demo'))
   self.assertEqual(counts['people'],7);self.assertEqual(counts['excluded']['do_not_contact'],1)
   brief=run('context','ava@trailnotes.example.com');self.assertIn('Ava',brief)
   cards=list((Path(td)/'conversations/vault').rglob('*.md'));self.assertGreater(len(cards),10)
   env.update(PYTHONPATH=str(R/'vendor/affiliate-manager-agent'),RELCORE_MODE='plugin',RELCORE_HOME=str(Path(td)/'conversations/hermes/data/relationship'),RELCORE_VAULT=str(Path(td)/'conversations/vault'))
   req=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}})+'\n'
   p=subprocess.run(['python3','-m','relcore.mcp_server','--mode','plugin'],env=env,input=req,text=True,capture_output=True)
   self.assertEqual(p.returncode,0,p.stderr)
   names=[t['name'] for t in json.loads(p.stdout.splitlines()[-1])['result']['tools']]
   self.assertIn('rel_context',names);self.assertNotIn('rel_send',names);self.assertNotIn('rel_approve',names)
