"""NAS members and per-share access; owner privileges are never inherited."""
from datetime import datetime,timezone
import json
from pathlib import Path


class Members:
    def __init__(self,app,run,error,password_record,atomic):
        self.app,self.run,self.error,self.password_record,self.atomic=app,run,error,password_record,atomic
        self.path=app.state/'members.json'
        self.records=json.loads(self.path.read_text()) if self.path.exists() else []

    def save(self):self.atomic(self.path,self.records)

    def public(self):
        owner=[] if not self.app.admin else [{'username':self.app.admin['username'],'role':'owner','enabled':True}]
        return owner+[{'username':r['username'],'role':'member','enabled':r.get('enabled',True),'created':r.get('created')} for r in self.records]

    def create(self,data):
        record=self.password_record(data.get('username',''),data.get('password',''))
        name=record['username']
        if any(r['username']==name for r in self.public()):raise self.error('That username is already in use.',409)
        if len(self.records)>=32:raise self.error('This server supports up to 32 additional members.',409)
        if not self.app.demo:
            import pwd
            try:pwd.getpwnam(name)
            except KeyError:pass
            else:raise self.error('That system account already exists.',409)
            self.run('useradd','--no-create-home','--shell','/usr/sbin/nologin',name)
            try:
                self.run('smbpasswd','-s','-a',name,input_text=data['password']+'\n'+data['password']+'\n')
            except Exception:
                self.run('userdel',name,check=False)
                raise
        record.update(enabled=True,created=datetime.now(timezone.utc).isoformat())
        with self.app.lock:self.records.append(record);self.save()
        self.app.event('Created member “'+name+'”.')
        return {'username':name,'role':'member','enabled':True}

    def enable(self,data):
        name=data.get('username');enabled=data.get('enabled')
        record=next((r for r in self.records if r['username']==name),None)
        if record is None or not isinstance(enabled,bool):raise self.error('Choose a member and an enabled state.')
        if not self.app.demo:self.run('smbpasswd','-e' if enabled else '-d',name)
        with self.app.lock:
            record['enabled']=enabled;self.save()
            self.app.sessions={token:s for token,s in self.app.sessions.items() if s['username']!=name}
        self.app.sync_samba()
        if not self.app.demo and not enabled:self.run('smbcontrol','smbd','close-denied-share','*',timeout=10)
        self.app.event(('Enabled' if enabled else 'Disabled')+' member “'+name+'”.')
        return {'username':name,'enabled':enabled}

    def allowed(self,share,name,write=False):
        if self.app.admin and name==self.app.admin['username']:return True
        record=next((r for r in self.records if r['username']==name and r.get('enabled',True)),None)
        if not record:return False
        mode=share.get('access',{}).get(name,'none')
        return mode=='write' or (mode=='read' and not write)

    def access(self,data):
        share=next((s for s in self.app.config['shares'] if s['name']==data.get('share')),None)
        value=data.get('access')
        names={r['username'] for r in self.records}
        if share is None or not isinstance(value,dict) or any(k not in names or v not in ('none','read','write') for k,v in value.items()):
            raise self.error('Invalid folder access settings.')
        with self.app.lock:
            share['access']={k:v for k,v in value.items() if v!='none'}
            self.app.save();self.app.sync_samba()
            if not self.app.demo:self.run('smbcontrol','smbd','close-share',share['name'],timeout=10)
        self.app.event('Updated access to “'+share['name']+'”.')
        return {'ok':True}
