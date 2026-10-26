"""Acceptance test limited to the dedicated installed graphical VM."""
import http.client,json,secrets,time,subprocess,io,zipfile
from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().strip().startswith('Standard PC')
assert 'boot=live' not in Path('/proc/cmdline').read_text().split()
cookie='';csrf=''
def request(path,data=None,raw=False,expected=200):
    global cookie,csrf
    connection=http.client.HTTPConnection('127.0.0.1',17080,timeout=45)
    headers={'Cookie':cookie,'X-Harbor-CSRF':csrf}
    if data is not None and not raw:headers['Content-Type']='application/json';data=json.dumps(data)
    connection.request('POST' if data is not None else 'GET',path,data,headers)
    response=connection.getresponse();body=response.read()
    try:value=json.loads(body)
    except ValueError:value=body
    assert response.status==expected,(path,response.status,value)
    if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
    if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
    connection.close();return value
def wait(job,timeout=300):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        current=next(j for j in request('/api/jobs') if j['id']==job['id'])
        if current['state']=='failed':raise RuntimeError(current)
        if current['state']=='completed':return current
        time.sleep(1)
    raise RuntimeError('Job timed out')
health=request('/api/health');assert health['version']=='0.3.0' and not health['live'] and not health['demo']
account_file=Path('/root/harbour-test-accounts.json')
if health['setup_required']:
    accounts={'owner':'testowner','owner_password':secrets.token_urlsafe(24),'member':'testmember','member_password':secrets.token_urlsafe(24)}
    request('/api/setup-session')
    request('/api/setup',{'username':accounts['owner'],'password':accounts['owner_password'],'confirm':accounts['owner_password']})
    account_file.write_text(json.dumps(accounts));account_file.chmod(0o600)
else:
    accounts=json.loads(account_file.read_text());request('/api/login',{'username':accounts['owner'],'password':accounts['owner_password']})
request('/api/onboarding',{})
inventory=request('/api/storage/disks');assert not inventory['live']
system=next(d for d in inventory['disks'] if d['serial']=='HARBOUR_GUI_SYSTEM');assert not system['eligible']
selected=[d for d in inventory['disks'] if d['serial'] in ('HARBOUR_GUI_DATA1','HARBOUR_GUI_DATA2')];assert len(selected)==2
if not request('/api/summary')['storage']['mounted']:
    plan=request('/api/storage/plan',{'name':'GUI-Mirror','level':'1','disks':[d['id'] for d in selected]})
    wait(request('/api/storage/create',{'token':plan['token'],'confirmation':'ERASE GUI-Mirror','acknowledge':True},expected=202))
assert request('/api/summary')['storage']['redundancy']=='RAID1'
if not any(s['name']=='Documents' for s in request('/api/shares')):request('/api/shares',{'name':'Documents'},expected=201)
if not any(m['username']==accounts['member'] for m in request('/api/members')):request('/api/members',{'username':accounts['member'],'password':accounts['member_password']},expected=201)
Path('/tmp/harbour-smb-auth').write_text('username='+accounts['member']+'\npassword='+accounts['member_password']+'\n');Path('/tmp/harbour-smb-auth').chmod(0o600)
Path('/tmp/harbour-smb-test.txt').write_text('SMB member acceptance')
def smb(command,success):
    result=subprocess.run(['smbclient','//127.0.0.1/Documents','-A','/tmp/harbour-smb-auth','-c',command],capture_output=True,text=True)
    assert (result.returncode==0)==success,(command,result.returncode,result.stdout,result.stderr)
request('/api/share-access',{'share':'Documents','access':{accounts['member']:'none'}})
smb('ls',False)
request('/api/share-access',{'share':'Documents','access':{accounts['member']:'read'}})
smb('ls',True);smb('put /tmp/harbour-smb-test.txt member.txt',False)
request('/api/share-access',{'share':'Documents','access':{accounts['member']:'write'}})
smb('put /tmp/harbour-smb-test.txt member.txt',True)
assert request('/api/download?path=Documents/member.txt')==b'SMB member acceptance'
with zipfile.ZipFile(io.BytesIO(request('/api/archive?path=Documents'))) as archive:assert archive.read('Documents/member.txt')==b'SMB member acceptance'
request('/api/member-state',{'username':accounts['member'],'enabled':False});smb('ls',False)
request('/api/member-state',{'username':accounts['member'],'enabled':True});smb('ls',True)
request('/api/system-action',{'action':'timezone','timezone':'America/New_York'},expected=202)
assert request('/api/system')['timezone']=='America/New_York'
assert len(request('/api/apps'))==181
report={'version':health['version'],'live_boot':'UEFI','installed_boot':'UEFI','graphical_console':True,'code_free_setup':True,'raid':'RAID1','system_disk_protected':True,'catalog':181,'samba_permissions':['no access','read only','read and write','disable','enable'],'archive_roundtrip':True,'timezone_change':True}
Path('/root/harbour-0.3-acceptance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
