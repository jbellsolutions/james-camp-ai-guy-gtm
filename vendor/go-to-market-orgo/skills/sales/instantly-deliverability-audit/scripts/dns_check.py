"""DNS deliverability checker for cold email domains.

Queries SPF, DKIM, and DMARC via Cloudflare DoH (no dig/nslookup required).
Checks BOTH default._domainkey and google._domainkey selectors.

Usage: python3 dns_check.py [domain1 domain2 ...]
If no domains given, uses a built-in default list (edit as needed).
"""

import json, sys, urllib.request

# Default domain list — edit this list or pass domains on command line.
# Example: python3 dns_check.py example.com test.org
DEFAULT_DOMAINS = []

CHECKS = [
    ('SPF', lambda d: d),
    ('DKIM-default', lambda d: f'default._domainkey.{d}'),
    ('DKIM-google', lambda d: f'google._domainkey.{d}'),
    ('DMARC', lambda d: f'_dmarc.{d}'),
]


def check_domain(domain):
    results = {}
    for label, qname_fn in CHECKS:
        qname = qname_fn(domain)
        url = f'https://cloudflare-dns.com/dns-query?name={qname}&type=TXT'
        req = urllib.request.Request(url, headers={'accept': 'application/dns-json'})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
            answers = [a['data'] for a in resp.get('Answer', [])]
            if label == 'SPF':
                # Cloudflare DoH returns ALL TXT records, not just the first.
                # Domains with google-site-verification + SPF have multiple records —
                # taking answers[0] blindly picks the wrong one. Find the v=spf1 record.
                spf = next((a for a in answers if 'v=spf1' in a), None)
                results[label] = spf if spf else (answers[0] if answers else 'MISSING')
            else:
                results[label] = answers[0] if answers else 'MISSING'
        except Exception as e:
            results[label] = f'ERROR: {e}'
    return results


def main():
    domains = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_DOMAINS

    all_ok = True
    for domain in domains:
        results = check_domain(domain)
        print(f'\n{domain}:')
        for label, value in results.items():
            is_spf = label == 'SPF'
            is_ok = value != 'MISSING' and not value.startswith('ERROR')
            # SPF needs actual v=spf1 record, not just any TXT
            if is_ok and is_spf and 'v=spf1' not in value:
                is_ok = False
                value = f'WARNING: NOT SPF: {value[:100]}'
            emoji = 'OK' if is_ok else 'FAIL'
            short = value[:150] + '...' if len(value) > 150 else value
            print(f'  [{emoji}] {label}: {short}')
            if not is_ok:
                all_ok = False

    print(f'\n{"="*50}')
    print('ALL CLEAN' if all_ok else 'ISSUES FOUND — review flagged domains above')
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
