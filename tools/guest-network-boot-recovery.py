"""Two VM reboot checks: confirmed bond persistence, then unconfirmed-change recovery."""
import http.client,json,subprocess,time
from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
credentials=json.loads(Path('/root/harbour-test-accounts.json').read_text());cookie='';csrf=''
def request(path,data=None):
    global cookie,csrf
    conn=http.client.HTTPConnection('127.0.0.1',17080,timeout=30);conn.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,{'Cookie':cookie,'X-Harbor-CSRF':csrf,'Content-Type':'application/json'})
    response=conn.getresponse();value=json.loads(response.read());assert response.status<400,(response.status,value)
    if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
    if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
    return value
def pending():
    for _ in range(60):
        state=request('/api/network')['transaction']
        if state.get('phase')=='awaiting_confirmation':return state
        if state['state']=='failed':raise RuntimeError(state)
        time.sleep(.25)
    raise RuntimeError('No pending network change')
def reboot():subprocess.run(['systemd-run','--collect','--on-active=3s','--unit=harbour-vm-boot-test','/usr/bin/systemctl','reboot'],check=True,capture_output=True)
request('/api/login',{'username':credentials['owner'],'password':credentials['owner_password']})
path=Path('/root/harbour-network-boot-phase.json');phase=json.loads(path.read_text()) if path.exists() else {'phase':0}
boot=Path('/proc/sys/kernel/random/boot_id').read_text()
report_path=Path('/root/harbour-maintenance-validation.json');report=json.loads(report_path.read_text())
if phase['phase']==0:
    info=request('/api/network');ports=[i['name'] for i in info['interfaces'] if i['eligible']]
    plan=request('/api/network-plan',{'mode':'active-backup','interfaces':ports,'primary':ports[0],'method':'dhcp'})
    request('/api/network-action',{'action':'apply','token':plan['token'],'confirmation':'APPLY'});state=pending();request('/api/network-action',{'action':'keep','id':state['id']})
    path.write_text(json.dumps({'phase':1,'boot':boot}));print('Confirmed bond saved; scheduling disposable VM reboot.',flush=True);reboot()
elif phase['phase']==1:
    assert phase['boot']!=boot;assert Path('/sys/class/net/bond0/bonding/mode').read_text().startswith('active-backup')
    assert request('/api/network')['config'] is not None
    report['confirmed_bond_survives_reboot']=True;report_path.write_text(json.dumps(report,indent=2))
    request('/api/network-action',{'action':'remove','confirmation':'APPLY'});pending()
    path.write_text(json.dumps({'phase':2,'boot':boot}));print('Bond persisted. Scheduling reboot with an unconfirmed removal.',flush=True);reboot()
else:
    assert phase['boot']!=boot;info=request('/api/network');assert info['transaction']['phase']=='rolled_back',info
    assert Path('/sys/class/net/bond0').exists() and info['config'] is not None
    start=subprocess.check_output(['systemctl','show','harbour-network-recover','--property=ExecMainStartTimestampMonotonic','--value'],text=True).strip();assert int(start)>0
    report['unconfirmed_change_restored_at_boot']=True
    request('/api/network-action',{'action':'remove','confirmation':'APPLY'});state=pending();request('/api/network-action',{'action':'keep','id':state['id']})
    path.write_text(json.dumps({'phase':3,'boot':boot}));report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
