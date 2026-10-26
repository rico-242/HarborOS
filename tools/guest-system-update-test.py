import http.client,json,time
from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
accounts=json.loads(Path('/root/harbour-test-accounts.json').read_text());cookie='';csrf=''
def request(path,data=None):
    global cookie,csrf
    conn=http.client.HTTPConnection('127.0.0.1',17080,timeout=30)
    conn.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,{'Cookie':cookie,'X-Harbor-CSRF':csrf,'Content-Type':'application/json'})
    response=conn.getresponse();value=json.loads(response.read());assert response.status<400,(response.status,value)
    if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
    if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
    return value
def wait(ident):
    for _ in range(900):
        try:job=next(j for j in request('/api/jobs') if j['id']==ident)
        except (OSError,StopIteration):time.sleep(1);continue
        if job['state']=='failed':raise RuntimeError(job)
        if job['state']=='completed':return job
        time.sleep(1)
    raise RuntimeError('Package job timed out')
request('/api/login',{'username':accounts['owner'],'password':accounts['owner_password']})
check=wait(request('/api/system-action',{'action':'check-updates'})['id']);print('Signed package check passed.',flush=True)
install=wait(request('/api/system-action',{'action':'install-updates','confirmation':'UPDATE'})['id']);print('Signed package upgrade passed.',flush=True)
report_path=Path('/root/harbour-0.3-acceptance.json');report=json.loads(report_path.read_text());report.update(signed_package_check=True,signed_package_upgrade=True);report_path.write_text(json.dumps(report,indent=2))
print(json.dumps(report))
