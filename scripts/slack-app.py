#!/usr/bin/env python3
"""Validate/create a Slack manifest. Secrets only from private env; responses saved privately."""
import argparse,json,os,urllib.request,urllib.parse
from pathlib import Path

def call(method,token,manifest):
    body=urllib.parse.urlencode({'manifest':json.dumps(manifest)}).encode()
    req=urllib.request.Request('https://slack.com/api/apps.manifest.'+method,data=body,headers={'Authorization':'Bearer '+token,'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req,timeout=30) as r:result=json.load(r)
    if not result.get('ok'):raise SystemExit('Slack returned '+str(result.get('error','unknown_error'))+'; inspect manifest/account permissions.')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('--create',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
    token=os.environ.get('SLACK_CONFIGURATION_TOKEN','')
    if not token:raise SystemExit('Private SLACK_CONFIGURATION_TOKEN required; owner can use Slack manifest UI instead.')
    if a.create and (not a.output or a.output.exists()):raise SystemExit('Create requires a new private --output path; existing receipt must be reconciled, not recreated.')
    manifest=json.loads(a.manifest.read_text());call('validate',token,manifest)
    if a.create:
        result=call('create',token,manifest);a.output.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump(result,f,indent=2)
        print(json.dumps({'app_id':result.get('app_id'),'private_receipt':str(a.output),'owner_workspace_consent':'required'}))
    else:print('Slack manifest validated')
