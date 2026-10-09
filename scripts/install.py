#!/usr/bin/env python3
"""Client-isolated two-install preparation and opt-in Linux deployment."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def managed(src,dest,previous,current,conflicts):
    dest.parent.mkdir(parents=True,exist_ok=True);key=str(dest)
    new=hashlib.sha256(src.read_bytes()).hexdigest()
    old=hashlib.sha256(dest.read_bytes()).hexdigest() if dest.exists() else None
    if old is None or old==new or old==previous.get(key):
        shutil.copy2(src,dest);current[key]=new
    else:
        current[key]=previous.get(key,old);conflicts.append(key)

def generated(text,dest,previous,current,conflicts):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        src=Path(td)/'asset';src.write_text(text);managed(src,dest,previous,current,conflicts)

def prepare(mode,state,affiliate=False):
    state=state.resolve();state.mkdir(parents=True,exist_ok=True);state.chmod(0o700)
    manifest=state/'assets-manifest.json';previous=json.loads(manifest.read_text()) if manifest.exists() else {};current=dict(previous);conflicts=[]
    selected=['cold-email','conversations'] if mode=='both' else [mode]
    roster=json.loads((ROOT/'profiles/manifest.json').read_text())
    defaults={'cold-email':('chief-sales-officer',18789,9900),'conversations':('conversion-specialist',18790,9901)}
    cfg={'model':{'provider':'custom','default':'accounts/fireworks/models/deepseek-v4-pro','base_url':'https://api.fireworks.ai/inference/v1','key_env':'FIREWORKS_API_KEY'},'approvals':{'mode':'manual'},'privacy':{'redact_pii':True},'security':{'redact_secrets':True},'agent':{'max_turns':60,'verify_on_stop':True},'gateway':{'platforms':{'slack':{'enabled':False},'telegram':{'enabled':False},'a2a':{'enabled':False}}},'platform_toolsets':{'cli':['terminal','file','web','browser','memory','skills','todo','clarify']},'terminal':{'cwd':'/vault'},'skills':{'write_approval':True,'guard_agent_created':True}}
    for install in selected:
        base=state/install;home=base/'hermes/data';home.mkdir(parents=True,exist_ok=True)
        env=base/'agent.env'
        if not env.exists():
            values={'AGENT_NAME':'james-'+install,'BASE_DIR':str(base),'HERMES_PORT':str(defaults[install][1]),'A2A_PUBLIC_PORT':str(defaults[install][2])}
            lines=[]
            for line in (ROOT/'vendor/go-to-market-orgo/agent.example.env').read_text().splitlines():
                key=line.split('=',1)[0];lines.append(key+'='+values[key] if key in values else line)
            env.write_text('\n'.join(lines)+'\nSLACK_ALLOWED_USERS=\nSMARTLEAD_API_KEY=\nGHL_API_KEY=\nGHL_LOCATION_ID=\n');env.chmod(0o600)
        chosen=[p for p in roster if p['install']==install or (install=='conversations' and affiliate and p['optional'])]
        for p in chosen:
            dest=home/'profiles'/p['id'];dest.mkdir(parents=True,exist_ok=True)
            if not (dest/'profile.yaml').exists():generated(json.dumps({'description':p['title'],'role':p['id']},indent=2)+'\n',dest/'profile.yaml',previous,current,conflicts)
            for name in ['SOUL.md','CHARTER.md']:
                text=(ROOT/'profiles'/p['id']/name).read_text().replace('../../docs/','')
                generated(text,dest/name,previous,current,conflicts)
            for name in ['WORKFLOW','TEAM-CONTRACT','SKILL-OVERLAY','CONTEXT-GRAPH','CSO']:
                managed(ROOT/'docs'/(name+'.md'),dest/(name+'.md'),previous,current,conflicts)
            managed(ROOT/'charters/PROJECT.md',dest/'PROJECT.md',previous,current,conflicts)
            for skill in p['skills']:
                locations={'instantly-cold-email':ROOT/'vendor/go-to-market-orgo/skills/sales/instantly-cold-email'}
                src=locations.get(skill,ROOT/'skills'/skill)
                for f in src.rglob('*'):
                    if f.is_file() and '__pycache__' not in f.parts:managed(f,dest/'skills'/skill/f.relative_to(src),previous,current,conflicts)
            profile_config=json.loads(json.dumps(cfg))
            if install=='conversations':
                profile_config['mcp_servers']={'relationships':{'command':'python3','args':['-m','relcore.mcp_server','--mode','plugin'],'env':{'PYTHONPATH':'/opt/james-gtm/vendor/affiliate-manager-agent','RELCORE_MODE':'plugin','RELCORE_HOME':'/opt/data/relationship','RELCORE_VAULT':'/vault','RELCORE_STOP_FILE':'/opt/data/EXTERNAL_WRITES_STOPPED','RELCORE_EMPLOYEE':p['id']},'trust':'untrusted','enabled':True}}
            if not (dest/'config.yaml').exists():generated(json.dumps(profile_config,indent=2)+'\n',dest/'config.yaml',previous,current,conflicts)
        if install=='cold-email':
            generated((ROOT/'config/cso-integration.example.json').read_text(),home/'cso/integration.json',previous,current,conflicts)
        supervisor=home/'profiles'/defaults[install][0]
        for name in ['SOUL.md','CHARTER.md','PROJECT.md','WORKFLOW.md','TEAM-CONTRACT.md','SKILL-OVERLAY.md','CONTEXT-GRAPH.md','CSO.md','config.yaml']:
            if name!='config.yaml' or not (home/name).exists():managed(supervisor/name,home/name,previous,current,conflicts)
        for f in (supervisor/'skills').rglob('*'):
            if f.is_file():managed(f,home/'skills'/f.relative_to(supervisor/'skills'),previous,current,conflicts)
        for skill in ['skill-creator','composio-cli','browser-box','data-box']:
            for f in (ROOT/'skills'/skill).rglob('*'):
                if f.is_file() and '__pycache__' not in f.parts:managed(f,home/'skills'/skill/f.relative_to(ROOT/'skills'/skill),previous,current,conflicts)
        (base/'vault').mkdir(exist_ok=True)
    manifest.write_text(json.dumps(current,indent=2)+'\n');manifest.chmod(0o600)
    return selected,conflicts


def patch_watchdog(path):
    text=path.read_text()
    guard='[ ! -e "$BASE_DIR/hermes/data/EXTERNAL_WRITES_STOPPED" ] || exit 0\n'
    if guard not in text:text=text.replace('mkdir -p "$STATEDIR"',guard+'mkdir -p "$STATEDIR"',1)
    if guard not in text:raise RuntimeError('Watchdog layout changed; cannot verify emergency-stop guard.')
    path.write_text(text)

def deploy(selected,state):
    if (state.resolve()/'EXTERNAL_WRITES_STOPPED').exists():raise RuntimeError('Emergency stop is active; reconcile and obtain owner-authorized recovery first.')
    if os.uname().sysname!='Linux':raise RuntimeError('Deploy on the selected Linux Orgo/VPS target.')
    subprocess.run(['docker','compose','version'],check=True,stdout=subprocess.DEVNULL)
    for install in selected:
        base=state.resolve()/install
        subprocess.run(['bash',str(ROOT/'vendor/go-to-market-orgo/new-agent.sh'),str(base/'agent.env'),'--no-start'],check=True)
        patch_watchdog(base/'bin/watchdog.sh')
        config=base/'hermes/data/config.yaml';cfg=json.loads(config.read_text());envtext=(base/'.env').read_text()
        def present(key):
            vals=[l.partition('=')[2].strip().strip('\"\'') for l in envtext.splitlines() if l.startswith(key+'=')];return bool(vals and vals[-1])
        if present('SLACK_BOT_TOKEN') and present('SLACK_APP_TOKEN'):
            if not present('SLACK_ALLOWED_USERS'):raise RuntimeError('Slack requires private owner Member IDs in SLACK_ALLOWED_USERS.')
            cfg['gateway']['platforms']['slack']['enabled']=True;cfg['platform_toolsets']['slack']=cfg['platform_toolsets']['cli']
        config.write_text(json.dumps(cfg,indent=2)+'\n');config.chmod(0o600)
        compose=base/'compose.yml';text=compose.read_text()
        text=text.replace('      INSTANTLY_API_KEY:', '      SLACK_ALLOWED_USERS: ${SLACK_ALLOWED_USERS:-}\n      SMARTLEAD_API_KEY: ${SMARTLEAD_API_KEY:-}\n      GHL_API_KEY: ${GHL_API_KEY:-}\n      GHL_LOCATION_ID: ${GHL_LOCATION_ID:-}\n      INSTANTLY_API_KEY:')
        text=text.replace('      - ${BASE_DIR}/logs:/logs','      - ${BASE_DIR}/logs:/logs\n      - '+str(ROOT)+':/opt/james-gtm:ro');compose.write_text(text)
        for args in [('config','--quiet'),('pull','hermes'),('up','-d','hermes'),('restart','hermes')]:subprocess.run(['docker','compose','--env-file','.env',*args],cwd=base,check=True)
        subprocess.run(['bash',str(ROOT/'scripts/verify-runtime.sh'),str(base)],check=True)
        manifest=state.resolve()/'assets-manifest.json'
        hashes=json.loads(manifest.read_text());hashes[str(config)]=hashlib.sha256(config.read_bytes()).hexdigest();manifest.write_text(json.dumps(hashes,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['cold-email','conversations','both'],default='both');p.add_argument('--state-root',type=Path,required=True);p.add_argument('--affiliate',action='store_true');g=p.add_mutually_exclusive_group(required=True);g.add_argument('--prepare-only',action='store_true');g.add_argument('--deploy',action='store_true');a=p.parse_args()
    selected,conflicts=prepare(a.mode,a.state_root,a.affiliate)
    print(json.dumps({'prepared':selected,'preserved_customizations':conflicts,'state_root':str(a.state_root.resolve()),'external_connections':'not verified'}))
    if a.deploy:
        if conflicts:raise SystemExit('Resolve preserved customizations before deploying; no customized files overwritten.')
        deploy(selected,a.state_root)
