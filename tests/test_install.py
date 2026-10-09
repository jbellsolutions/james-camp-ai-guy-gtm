import json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from install import prepare,patch_watchdog
class InstallTests(unittest.TestCase):
 def test_isolation_rerun_and_customization(self):
  with tempfile.TemporaryDirectory() as td:
   state=Path(td).resolve();_,conflicts=prepare('both',state);self.assertEqual(conflicts,[])
   self.assertEqual(len(list((state/'cold-email/hermes/data/profiles').iterdir())),9);self.assertEqual(len(list((state/'conversations/hermes/data/profiles').iterdir())),3)
   self.assertTrue((state/'cold-email/hermes/data/profiles/chief-sales-officer/CSO.md').exists())
   self.assertIn('Chief Sales Officer',(state/'cold-email/hermes/data/SOUL.md').read_text())
   self.assertIn('Conversion Specialist',(state/'conversations/hermes/data/SOUL.md').read_text())
   for mode,port in [('cold-email',18789),('conversations',18790)]:
    self.assertIn('HERMES_PORT='+str(port),(state/mode/'agent.env').read_text());self.assertEqual((state/mode/'agent.env').stat().st_mode&0o777,0o600)
   config=state/'conversations/hermes/data/config.yaml';cfg=json.loads(config.read_text());cfg['mcp_servers']['custom-tool']={'enabled':True};config.write_text(json.dumps(cfg))
   self.assertEqual(prepare('both',state)[1],[]);self.assertTrue(json.loads(config.read_text())['mcp_servers']['custom-tool']['enabled'])
   soul=state/'cold-email/hermes/data/profiles/gtm-writer/SOUL.md';soul.write_text('custom');db=state/'keep.db';db.write_bytes(b'unchanged')
   _,conflicts=prepare('both',state);self.assertIn(str(soul),conflicts);self.assertEqual(soul.read_text(),'custom');self.assertEqual(db.read_bytes(),b'unchanged')
 def test_affiliate_optional(self):
  with tempfile.TemporaryDirectory() as td:
   state=Path(td).resolve();prepare('conversations',state);p=state/'conversations/hermes/data/profiles/affiliate-manager';self.assertFalse(p.exists());prepare('conversations',state,True);self.assertTrue((p/'CHARTER.md').exists())
 def test_preparation_never_enables_channels(self):
  with tempfile.TemporaryDirectory() as td:
   state=Path(td).resolve();prepare('both',state)
   for f in state.rglob('config.yaml'):
    cfg=json.loads(f.read_text());self.assertFalse(cfg['gateway']['platforms']['slack']['enabled']);self.assertFalse(cfg['gateway']['platforms']['a2a']['enabled'])

 def test_emergency_stop_prevents_watchdog_restart(self):
  import subprocess
  from install import ROOT
  with tempfile.TemporaryDirectory() as td:
   base=Path(td);(base/'hermes/data').mkdir(parents=True);(base/'hermes/data/EXTERNAL_WRITES_STOPPED').touch()
   watchdog=base/'watchdog.sh';text=(ROOT/'vendor/go-to-market-orgo/bin/watchdog.sh').read_text().replace('__AGENT_NAME__','synthetic').replace('__BASE_DIR__',str(base));watchdog.write_text(text);patch_watchdog(watchdog)
   result=subprocess.run(['bash',str(watchdog)],text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stderr);self.assertFalse((base/'.watchdog').exists());self.assertEqual(result.stderr,'')
