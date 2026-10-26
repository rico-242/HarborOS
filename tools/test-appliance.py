#!/usr/bin/env python3
"""End-to-end appliance checks, run on the build host against the private VM."""
import hashlib
import http.client
import json
from pathlib import Path
import re
import ssl
import sys
import time

password = sys.stdin.readline().rstrip('\n')
if not password:
    raise SystemExit('Missing password on stdin.')
serial = Path('/DATA/harbor/vm/serial.log').read_text(errors='replace')
codes = re.findall(r'First-time setup code: ([0-9a-f]{48})', serial)
fingerprints = re.findall(r'sha256 Fingerprint=([0-9A-F:]{95})', serial, re.IGNORECASE)
if not fingerprints:
    raise SystemExit('The trusted VM console has not reported its TLS fingerprint yet.')
expected = fingerprints[-1].replace(':', '').lower()
cookie = ''
csrf = ''


def request(path, data=None, raw=False):
    global cookie, csrf
    # Verify the exact certificate through the already-authenticated host console
    # before sending any credentials. This is certificate pinning, not trust-all.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    conn = http.client.HTTPSConnection('127.0.0.1', 18443, context=context, timeout=30)
    conn.connect()
    actual = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
    if actual != expected:
        conn.close()
        raise SystemExit('TLS certificate does not match the trusted VM console.')
    headers = {'Cookie':cookie, 'X-Harbor-CSRF':csrf}
    if data is not None and not raw:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(data)
    conn.request('POST' if data is not None else 'GET', path, data, headers)
    response = conn.getresponse()
    body = response.read()
    if response.getheader('Set-Cookie'):
        cookie = response.getheader('Set-Cookie').split(';')[0]
    try:
        value = json.loads(body)
    except ValueError:
        value = body
    status = response.status
    conn.close()
    if status >= 400:
        raise RuntimeError(f'{path}: {status}: {value}')
    return value


def job_done(job, limit=60):
    for _ in range(limit):
        item = next(j for j in request('/api/jobs') if j['id'] == job['id'])
        if item['state'] == 'failed':
            raise RuntimeError(item['error'])
        if item['state'] == 'completed':
            return item.get('result')
        time.sleep(1)
    raise RuntimeError('Job did not complete in time.')


health = request('/api/health')
assert health['name'] == 'Harbor OS' and not health['demo'], health
if health['setup_required']:
    assert codes, 'No setup code in trusted console'
    session = request('/api/setup', {'username':'rico', 'password':password, 'code':codes[-1]})
else:
    session = request('/api/login', {'username':'rico','password':password})
csrf = session['csrf']
print('PASS: pinned TLS, administrator setup/sign-in, secure session')
summary = request('/api/summary')
assert summary['storage']['mounted'], summary
assert summary['storage']['filesystem'] == 'btrfs', summary
assert summary['memory']['total'] > 1_000_000_000, summary
print('PASS: real Linux metrics and mounted Btrfs data volume')
name = 'Verification' + str(int(time.time()))
request('/api/shares', {'name': name})
request('/api/upload?path=' + name + '&name=integrity.txt', b'Harbor appliance integrity check\n', raw=True)
content = request('/api/download?path=' + name + '/integrity.txt')
assert content == b'Harbor appliance integrity check\n', content
print('PASS: real shared subvolume and byte-for-byte upload/download')
snapshot = job_done(request('/api/snapshots', {'share':name}))
restored = name + 'Restored'
job_done(request('/api/restore', {'snapshot':snapshot['id'], 'name':restored}))
assert request('/api/download?path=' + restored + '/integrity.txt') == content
print('PASS: read-only Btrfs snapshot and non-destructive restore, content verified')
assert request('/api/apps'), 'Missing app catalog'
print('PASS: Docker app engine and curated catalog')
if '--app' in sys.argv:
    installed = next(item for item in request('/api/apps') if item['id'] == 'jellyfin')
    if not installed['installed']:
        job_done(request('/api/app-action', {'id':'jellyfin', 'action':'install'}), limit=900)
    installed = next(item for item in request('/api/apps') if item['id'] == 'jellyfin')
    assert installed['state'] == 'running', installed
    print('PASS: Jellyfin image pull, installation, and running container')
request('/api/logout', {})
print('Appliance verification complete.')
