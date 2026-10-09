#!/usr/bin/env python3
"""Mechanical rendered-email QC. Claim truth and editorial independence remain human/agent checks."""
import argparse,hashlib,json,re,sys
from pathlib import Path

def check(data):
    errors=[]
    if not data.get('list_version') or not data.get('copy_version'):errors.append('Missing list/copy versions')
    emails=data.get('emails')
    if not isinstance(emails,list) or not emails:return ['Rendered emails required']+errors
    for i,e in enumerate(emails):
        if not isinstance(e,dict):errors.append(f'{i}: invalid email');continue
        if not e.get('recipient') or not e.get('subject') or not e.get('body'):errors.append(f'{i}: recipient/subject/body required')
        subject=str(e.get('subject',''));body=str(e.get('body',''))
        if re.match(r'^\s*(re:|fw:|fwd:)',subject,re.I):errors.append(f'{i}: deceptive reply/forward subject')
        if re.search(r'\{[^}]*\}|\[NEEDS:',subject+' '+body):errors.append(f'{i}: unresolved rendered token')
        if not e.get('evidence'):errors.append(f'{i}: research/claim review evidence required')
    return errors

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);a=p.parse_args();raw=a.artifact.read_bytes();errors=check(json.loads(raw))
    print(json.dumps({'status':'FAIL' if errors else 'PASS','sha256':hashlib.sha256(raw).hexdigest(),'errors':errors,'scope':'mechanical QC only; independent Editorial still required'},indent=2));sys.exit(bool(errors))
