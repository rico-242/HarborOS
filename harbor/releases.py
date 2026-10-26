"""Signed local updates and owner-configured public/private GitHub releases."""
import hashlib,json,os,re,secrets
from datetime import datetime,timezone
from pathlib import Path
from release_bundle import inspect_bundle,version,LIMIT

from github_source import GitHubSource
from github_releases import github_open

class Releases(GitHubSource):
    def __init__(self,app,run,error,atomic,current):
        self.app,self.run,self.error,self.atomic,self.current=app,run,error,atomic,current
        self.root=app.state/'release-updates'
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True);self.root.chmod(0o700)
        for name in ('incoming','candidates','jobs','requests'):(self.root/name).mkdir(mode=0o700,parents=True,exist_ok=True)
        self.key=Path('/etc/harbor/update-public.pem');self.config=self.root/'source.json';self.check_file=self.root/'check.json'
        self.credential=self.root/'github-credential.json'
        if self.credential.exists():self.credential.chmod(0o600)
    def status(self):
        values=[]
        for path in sorted((self.root/'jobs').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
            try:value=json.loads(path.read_text())
            except (ValueError,OSError):continue
            if re.fullmatch('[a-f0-9]{16}',value.get('id','')):self.app.jobs[value['id']]=value;values.append(value)
        return values
    def info(self):
        source,token=self.source()
        metadata=self.app.state/'release-state.json';installed=json.loads(metadata.read_text()) if metadata.exists() else {}
        candidates=[json.loads(p.read_text()) for p in sorted((self.root/'candidates').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)]
        return {'current':self.current,'previous':(installed.get('previous') or {}).get('version'),'trusted_key':self.key.exists(),
            'key_fingerprint':hashlib.sha256(self.key.read_bytes()).hexdigest() if self.key.exists() else None,
            'repository':source.get('repository',''),'include_prereleases':source.get('include_prereleases',False),'token_configured':bool(token),
            'check':json.loads(self.check_file.read_text()) if self.check_file.exists() else None,'jobs':self.status(),
            'candidates':[c for c in candidates if version(c['version'])>version(self.current)][:5]}
    def stage(self,path,ident):
        try:manifest,_=inspect_bundle(path,self.key,self.current)
        except Exception as error:raise self.error(str(error),409)
        value={'id':ident,'version':manifest['version'],'notes':str(manifest.get('notes',''))[:16000],'verified':True,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'created':datetime.now(timezone.utc).isoformat()}
        self.atomic(self.root/'candidates'/(ident+'.json'),value);return value
    def receive(self,reader,length):
        if self.app.demo:raise self.error('Release updates are available on the installed appliance.',409)
        if not self.key.exists():raise self.error('Install the trusted Harbour public key on the appliance first.',409)
        if not 0<length<=LIMIT:raise self.error('Choose a signed update bundle smaller than 64 MiB.',413)
        ident=secrets.token_hex(16);path=self.root/'incoming'/(ident+'.bundle')
        try:
            with path.open('xb') as stream:
                remaining=length
                while remaining:
                    data=reader.read(min(1024**2,remaining))
                    if not data:raise self.error('The update upload was interrupted.')
                    stream.write(data);remaining-=len(data)
                stream.flush();os.fsync(stream.fileno())
            return self.stage(path,ident)
        except Exception:path.unlink(missing_ok=True);raise
    def action(self,data):
        if self.app.demo:raise self.error('Release changes are disabled in the preview.',409)
        action=data.get('action')
        if action in ('source','check','download'):return self.github_action(action,data)
        if action not in ('install','rollback'):raise self.error('Unknown Harbour update operation.')
        with self.app.lock:
            self.app.system_settings.external_status()
            if any(j['state'] in ('queued','running') for j in self.app.jobs.values()):raise self.error('Finish the current task or pending network change first.',409)
            if action=='install':
                candidate=data.get('candidate','')
                if not re.fullmatch('[a-f0-9]{32}',candidate):raise self.error('Choose a verified update bundle.')
                receipt=self.root/'candidates'/(candidate+'.json')
                if not receipt.exists():raise self.error('The verified bundle is unavailable.')
                record=json.loads(receipt.read_text())
                if data.get('confirmation')!='UPDATE '+record['version']:raise self.error('Confirm the exact release version before installing.')
                # Recheck both signature and compatibility immediately before queuing.
                self.stage(self.root/'incoming'/(candidate+'.bundle'),candidate)
            else:
                if not self.info()['previous'] or data.get('confirmation')!='ROLLBACK':raise self.error('Type ROLLBACK to restore the previous Harbour release.')
                candidate=None
            ident=secrets.token_hex(8);job={'id':ident,'title':'Install Harbour release' if action=='install' else 'Restore previous Harbour release','kind':'release','state':'queued','actor':self.app.admin['username'],'external':True,'created':datetime.now(timezone.utc).isoformat(),'stage':'Queued for update'}
            self.atomic(self.root/'requests'/(ident+'.json'),{'action':action,'candidate':candidate+'.bundle' if candidate else None,'job':job})
            self.atomic(self.root/'jobs'/(ident+'.json'),job)
            try:self.run('systemd-run','--collect','--on-active=3s','--unit=harbour-release-'+ident,'/usr/local/sbin/harbour-release-update',ident)
            except Exception:
                job.update(state='failed',error='The update worker could not start.');self.atomic(self.root/'jobs'/(ident+'.json'),job);raise
            self.app.jobs[ident]=job;return job
