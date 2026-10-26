"""Exercise real signed upgrades/rollback and a two-NIC bond in the disposable VM."""
import hashlib,http.client,json,subprocess,time
from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
accounts=json.loads(Path('/root/harbour-test-accounts.json').read_text());cookie='';csrf=''
def request(path,data=None,raw=False):
    global cookie,csrf
    conn=http.client.HTTPConnection('127.0.0.1',17080,timeout=40);headers={'Cookie':cookie,'X-Harbor-CSRF':csrf}
    if data is not None:headers['Content-Type']='application/octet-stream' if raw else 'application/json'
    conn.request('POST' if data is not None else 'GET',path,data if raw else json.dumps(data) if data is not None else None,headers)
    response=conn.getresponse();body=response.read();value=json.loads(body)
    if response.status==401:raise PermissionError('Session must reconnect')
    if response.status>=400:raise RuntimeError((path,response.status,value))
    if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
    if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
    return value
def login():return request('/api/login',{'username':accounts['owner'],'password':accounts['owner_password']})
def wait(job,timeout=180):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            value=next(j for j in request('/api/jobs') if j['id']==job['id'])
            if value['state'] in ('failed','completed'):return value
        except (PermissionError,OSError,http.client.HTTPException):
            try:login()
            except (OSError,http.client.HTTPException,PermissionError):pass
        time.sleep(.5)
    raise RuntimeError('Timed out waiting for '+job['id'])
def await_network(phase):
    end=time.monotonic()+45
    while time.monotonic()<end:
        data=request('/api/network');state=data['transaction']
        if state and state.get('phase')==phase:return data
        if state and state['state']=='failed':raise RuntimeError(state)
        time.sleep(.5)
    raise RuntimeError('Network did not reach '+phase)
login();assert request('/api/health')['version']=='0.3.1'
original_admin=hashlib.sha256(Path('/var/lib/harbor/admin.json').read_bytes()).hexdigest()
original_storage=request('/api/summary')['storage']['source']
candidate=request('/api/os-updates/upload',Path('/tmp/harbour-0.4.0-update.bundle').read_bytes(),raw=True)
result=wait(request('/api/os-updates/action',{'action':'install','candidate':candidate['id'],'confirmation':'UPDATE 0.4.0'}));assert result['state']=='completed',result
assert request('/api/health')['version']=='0.4.0';login()
assert hashlib.sha256(Path('/var/lib/harbor/admin.json').read_bytes()).hexdigest()==original_admin
assert request('/api/summary')['storage']['source']==original_storage
print('Signed upgrade to 0.4.0 passed; login and RAID storage preserved.',flush=True)
result=wait(request('/api/os-updates/action',{'action':'rollback','confirmation':'ROLLBACK'}));assert result['state']=='completed',result
assert request('/api/health')['version']=='0.3.1';login()
result=wait(request('/api/os-updates/action',{'action':'install','candidate':candidate['id'],'confirmation':'UPDATE 0.4.0'}));assert result['state']=='completed',result
login();print('Explicit rollback and re-upgrade passed.',flush=True)
network=request('/api/network');ports=[i['name'] for i in network['interfaces'] if i['eligible']]
assert len(ports)==2,network
plan=request('/api/network-plan',{'mode':'active-backup','interfaces':ports,'primary':ports[0],'method':'dhcp'})
request('/api/network-action',{'action':'apply','token':plan['token'],'confirmation':'APPLY'})
pending=await_network('awaiting_confirmation');ident=pending['transaction']['id']
assert Path('/sys/class/net/bond0/bonding/mode').read_text().startswith('active-backup')
for _ in range(20):
    if any(i['name']=='bond0' and i['addresses'] for i in request('/api/network')['interfaces']):break
    time.sleep(.5)
else:raise RuntimeError('Bond did not receive an address')
request('/api/network-action',{'action':'keep','id':ident})
active=Path('/sys/class/net/bond0/bonding/active_slave').read_text().strip()
subprocess.run(['ip','link','set',active,'down'],check=True)
for _ in range(20):
    replacement=Path('/sys/class/net/bond0/bonding/active_slave').read_text().strip()
    if replacement and replacement!=active:break
    time.sleep(.2)
else:raise RuntimeError('Active-backup did not switch members')
subprocess.run(['ping','-I','bond0','-c','2','-W','2','10.0.2.2'],check=True,capture_output=True)
subprocess.run(['ip','link','set',active,'up'],check=True)
print('Bond creation, DHCP, confirmation and physical-link failover passed.',flush=True)
request('/api/network-action',{'action':'remove','confirmation':'APPLY'});pending=await_network('awaiting_confirmation');request('/api/network-action',{'action':'keep','id':pending['transaction']['id']})
assert not Path('/sys/class/net/bond0').exists()
network=request('/api/network');ports=[i['name'] for i in network['interfaces'] if i['eligible']]
plan=request('/api/network-plan',{'mode':'802.3ad','interfaces':ports,'primary':ports[0],'method':'dhcp','switch_ready':True})
request('/api/network-action',{'action':'apply','token':plan['token'],'confirmation':'APPLY'});pending=await_network('awaiting_confirmation')
assert Path('/sys/class/net/bond0/bonding/mode').read_text().startswith('802.3ad')
report={'signed_upgrade':True,'explicit_rollback':True,'reupgrade':True,'account_preserved':True,'storage_preserved':True,'active_backup_dhcp':True,'link_failover':True,'confirmed_bond_removal':True,'lacp_kernel_mode':True,'lacp_switch_throughput_tested':False,'timeout_transaction':pending['transaction']['id']}
Path('/root/harbour-maintenance-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
