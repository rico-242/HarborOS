import http.client,json,subprocess
connection=http.client.HTTPConnection('127.0.0.1',17081)
def request(path,data=None,headers=None):
    connection.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,headers or {})
    response=connection.getresponse();value=json.loads(response.read());assert response.status<400,(response.status,value)
    return value,dict(response.getheaders())
session,headers=request('/api/session')
auth={'Cookie':headers['Set-Cookie'].split(';')[0],'X-Harbor-CSRF':session['csrf'],'Content-Type':'application/json'}
disks,_=request('/api/disks');assert len(disks)==1,disks
disk=disks[0];assert disk['serial']=='HARBOUR_GUI_SYSTEM',disk
plan,_=request('/api/plan',{'disk':disk['id']},auth)
result,_=request('/api/install',{'plan':plan['id'],'erase':True},auth)
print(json.dumps({'graphical_services':subprocess.getoutput('systemctl is-active lightdm harbor harbor-installer'),'disk':disk,'install_started':result}))
