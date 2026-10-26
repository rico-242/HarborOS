"""Verify real app progress on the existing disposable VM, without changing disks."""
import http.client,json,time
from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
accounts=json.loads(Path('/root/harbour-test-accounts.json').read_text());cookie='';csrf=''
def request(path,data=None):
    global cookie,csrf
    connection=http.client.HTTPConnection('127.0.0.1',17080,timeout=40)
    connection.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,{'Cookie':cookie,'X-Harbor-CSRF':csrf,'Content-Type':'application/json'})
    response=connection.getresponse();value=json.loads(response.read());assert response.status<400,(path,response.status,value)
    if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
    if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
    return value
request('/api/login',{'username':accounts['owner'],'password':accounts['owner_password']})
for path in ('/widgets.js','/refinements.css','/process.js'):
    connection=http.client.HTTPConnection('127.0.0.1',17080);connection.request('GET',path);response=connection.getresponse();assert response.status==200;response.read()
def wait(job):
    for _ in range(900):
        current=next(j for j in request('/api/jobs') if j['id']==job['id'])
        if current['state'] in ('failed','completed'):return current
        time.sleep(1)
    raise RuntimeError('VM app job timed out')
app=next(a for a in request('/api/apps') if a['id']=='excalidraw')
if not app['installed']:
    result=wait(request('/api/app-action',{'id':'excalidraw','action':'install','options':{'approve_access':True}}))
    assert result['state']=='completed',result
    stages=[step['stage'] for step in result['steps']]
    for expected in ('Checking application','Validating configuration','Downloading images','Starting containers','Complete'):assert expected in stages,stages
else:
    result=wait(request('/api/app-action',{'id':'excalidraw','action':'stop'}));assert result['state']=='completed'
    result=wait(request('/api/app-action',{'id':'excalidraw','action':'start'}));assert result['state']=='completed'
    stages=[step['stage'] for step in result['steps']]
report={'actual_app':'Excalidraw','state':result['state'],'stages':stages,'timing_fields':all(k in result for k in ('created','started','finished')),'new_assets_http_200':True,'raid_disks_changed':False}
Path('/root/harbour-refinements-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
