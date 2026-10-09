#!/usr/bin/env python3
import ast,json,re,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];errors=[]
for f in R.rglob('*.json'):
 try:json.loads(f.read_text())
 except Exception as e:errors.append(str(f.relative_to(R))+': '+str(e))
for f in (R/'scripts').glob('*.py'):
 try:ast.parse(f.read_text())
 except SyntaxError as e:errors.append(str(e))
for f in (R/'scripts').glob('*.sh'):
 if subprocess.run(['bash','-n',str(f)],capture_output=True).returncode:errors.append('Shell syntax: '+str(f))
roster=json.loads((R/'profiles/manifest.json').read_text());assert len(roster)==13
for p in roster:
 for name in ['CHARTER.md','SOUL.md']:
  if not (R/'profiles'/p['id']/name).exists():errors.append('Missing '+p['id']+'/'+name)
link_files=list(R.glob('*.md'))
for folder in ['docs','profiles','charters']:
 link_files.extend((R/folder).rglob('*.md'))
for f in link_files:
  for target in re.findall(r'\]\(([^)]+)\)',f.read_text()) + re.findall(r'<img[^>]+src="([^"]+)"',f.read_text()):
   if '://' in target or target.startswith('#'):continue
   if not (f.parent/target.split('#')[0]).exists():errors.append('Broken link: '+str(f.relative_to(R))+' -> '+target)
for name in sorted({s for p in roster for s in p['skills']} | {'skill-creator','composio-cli'}):
 text=(R/'skills'/name/'SKILL.md').read_text()
 if not text.startswith('---\n') or 'description:' not in text.split('---',2)[1]:errors.append('Skill frontmatter: '+name)
if errors:print('\n'.join(errors));sys.exit(1)
print('Package contracts, JSON, script syntax and client links PASS')
