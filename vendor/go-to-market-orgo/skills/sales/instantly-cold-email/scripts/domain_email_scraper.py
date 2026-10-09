#!/usr/bin/env python3
"""Scrape domains for emails/phones. Checkpoint-aware, resumable.
Usage: python3 domain_email_scraper.py <domains.txt> <output.json>

Environment: set TIMEOUT_SEC (default 5), WORKERS (default 30), BATCH_SIZE (default 300)
"""
import urllib.request, re, time, concurrent.futures, json, os, sys

INPUT = sys.argv[1] if len(sys.argv) > 1 else '/tmp/domains.txt'
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else '/tmp/domain_emails.json'
CHECKPOINT = OUTPUT.replace('.json', '_checkpoint.json')

TIMEOUT = int(os.environ.get('TIMEOUT_SEC', '5'))
WORKERS = int(os.environ.get('WORKERS', '30'))
BATCH = int(os.environ.get('BATCH_SIZE', '300'))

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

# Known fake emails that appear in WordPress/theme templates
FAKE_EMAILS = {
    'name@email.com', 'user@domain.com', 'filler@godaddy.com', 'email@example.com',
    'test@test.com', 'test@example.com', 'your@email.com', 'you@example.com',
    'mail@example.com', 'example@example.com', 'someone@example.com',
    'user@example.com', 'hello@example.com', 'email@domain.com',
}
FAKE_DOMAINS = {'email.com', 'domain.com', 'example.com', 'test.com', 'godaddy.com', 'mail.com'}
THEME_KEYWORDS = ['aldusleaf', 'impallari', 'theme', 'wordpress', 'templatemonster']
GENERIC_PREFIXES = {
    'info','contact','support','admin','hello','sales','office','mail','general',
    'inquiries','enquiries','team','service','help','webmaster','postmaster',
    'noreply','no-reply','billing','accounts','hr','jobs','careers','marketing',
    'press','media','legal','abuse','security','reception','frontdesk',
    'administrator','assistant'
}
PERSONAL_DOMAINS = {
    'gmail.com','yahoo.com','outlook.com','hotmail.com','aol.com',
    'icloud.com','protonmail.com','fastmail.fm','live.com','msn.com'
}

def is_generic(prefix):
    if prefix in GENERIC_PREFIXES:
        return True
    return any(prefix.startswith(g) for g in ['info-','contact-','noreply','no-reply','donotreply'])

def scrape(domain):
    r = {'domain': domain, 'emails': [], 'phones': [], 'status': 'error'}
    for scheme in ['https://', 'http://']:
        try:
            req = urllib.request.Request(f"{scheme}{domain}",
                headers={'User-Agent': UA, 'Accept': 'text/html'})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                html = resp.read().decode('utf-8', errors='ignore')[:200000]
                raw_emails = list(set(re.findall(
                    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)))
                phones = list(set(re.findall(
                    r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', html)))

                emails = []
                for e in raw_emails:
                    el = e.lower()
                    if el in FAKE_EMAILS:
                        continue
                    ed = el.split('@')[1] if '@' in el else ''
                    if ed in FAKE_DOMAINS:
                        continue
                    if any(kw in el for kw in THEME_KEYWORDS):
                        continue
                    if is_generic(el.split('@')[0]):
                        continue
                    # Cross-domain check
                    domain_parts = domain.split('.')
                    if len(domain_parts) >= 2:
                        main = '.'.join(domain_parts[-2:])
                        if not ed.endswith(main) and ed not in PERSONAL_DOMAINS \
                           and not ed.endswith('.' + main):
                            continue
                    emails.append(el)

                r['emails'] = emails
                r['phones'] = phones
                r['status'] = 'ok'
                break
        except:
            continue
    return r

# Load + resume
with open(INPUT) as f:
    all_domains = [line.strip() for line in f if line.strip()]

done_domains = set()
all_results = []
if os.path.exists(CHECKPOINT):
    with open(CHECKPOINT) as f:
        saved = json.load(f)
        all_results = saved.get('results', [])
        done_domains = {r['domain'] for r in all_results}
    print(f"Resuming: {len(all_results)} done, {len(all_domains)-len(done_domains)} remaining")

remaining = [d for d in all_domains if d not in done_domains]
start = time.time()

for bi in range(0, len(remaining), BATCH):
    batch = remaining[bi:bi+BATCH]
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(scrape, d): d for d in batch}
        for f in concurrent.futures.as_completed(futures):
            all_results.append(f.result())

    elapsed = time.time() - start
    done = len(all_results)
    emails = sum(len(r['emails']) for r in all_results)
    pct = done / len(all_domains) * 100
    print(f"[{done}/{len(all_domains)}] {pct:.0f}% | {done/(elapsed+0.01):.1f} dom/s | {emails} emails", flush=True)

    with open(CHECKPOINT, 'w') as f:
        json.dump({'results': all_results, 'total_emails': emails}, f)

total = sum(len(r['emails']) for r in all_results)
oks = sum(1 for r in all_results if r['status'] == 'ok')
with open(OUTPUT, 'w') as f:
    json.dump(all_results, f)

print(f"DONE: {oks}/{len(all_domains)} OK | {total} emails | {time.time()-start:.0f}s", flush=True)
