import http.client,json,time,subprocess,urllib.request
from pathlib import Path
accounts=json.loads(Path('/root/harbour-test-accounts.json').read_text());cookie='';csrf=''
def request(path,data=None):
    global cookie,csrf
    conn=http.client.HTTPConnection('127.0.0.1',17080,timeout=45)
    conn.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,{'Cookie':cookie,'X-Harbor-CSRF':csrf,'Content-Type':'application/json'})
    response=conn.getresponse();value=json.loads(response.read());assert response.status<400,(path,response.status,value)
    if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
    if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
    return value
def wait(job):
    for _ in range(900):
        current=next(j for j in request('/api/jobs') if j['id']==job['id'])
        if current['state']=='failed':raise RuntimeError(current)
        if current['state']=='completed':return current
        time.sleep(1)
    raise RuntimeError('App job timed out')
request('/api/login',{'username':accounts['owner'],'password':accounts['owner_password']})
report_path=Path('/root/harbour-0.3-acceptance.json');report=json.loads(report_path.read_text());assert report['before_reboot_id']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert request('/api/summary')['storage']['mounted']
disks=request('/api/storage/disks')['disks'];assert all(not d['eligible'] for d in disks if d['serial'] in ('HARBOUR_GUI_DATA1','HARBOUR_GUI_DATA2','HARBOUR_GUI_SYSTEM'))
assert subprocess.getoutput('systemctl is-active lightdm harbor smbd docker').splitlines()==['active']*4
assert not Path('/etc/systemd/system/getty@tty2.service.d/harbor-live.conf').exists()
wait(request('/api/snapshots',{'share':'Documents'}))
assert request('/api/snapshots')
app=next(a for a in request('/api/apps') if a['id']=='syncthing')
if not app['installed']:wait(request('/api/app-action',{'id':'syncthing','action':'install','options':{'approve_access':True}}))
wait(request('/api/app-action',{'id':'syncthing','action':'stop'}));wait(request('/api/app-action',{'id':'syncthing','action':'start'}))
assert next(a for a in request('/api/apps') if a['id']=='syncthing')['state']=='running'
report.update(owner_reboot_control=True,storage_persistence=True,all_raid_members_protected=True,installed_no_root_autologin=True,snapshots=True,app_install_stop_start='Syncthing')
report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
