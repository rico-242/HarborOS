"""Signed local updates and an optional public GitHub Releases source."""
import hashlib,json,os,re,secrets,time,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from release_bundle import inspect_bundle,version,LIMIT

REPO=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z')
class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        url=urllib.parse.urlsplit(newurl)
        if url.scheme!='https' or url.hostname not in ('github.com','release-assets.githubusercontent.com','objects.githubusercontent.com') or url.username or url.password:raise ValueError('GitHub redirected outside its permitted asset hosts.')
        return super().redirect_request(request,fp,code,msg,headers,newurl)
def github_open(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ('api.github.com','github.com') or parsed.username or parsed.password:raise ValueError('Use an official GitHub HTTPS release URL.')
    return urllib.request.build_opener(GitHubRedirect()).open(urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'Harbour-OS-Updater','X-GitHub-Api-Version':'2022-11-28'}),timeout=30)

class Releases:
    def __init__(self,app,run,error,atomic,current):
        self.app,self.run,self.error,self.atomic,self.current=app,run,error,atomic,current
        self.root=app.state/'release-updates'
        for name in ('incoming','candidates','jobs','requests'):(self.root/name).mkdir(mode=0o700,parents=True,exist_ok=True)
        self.key=Path('/etc/harbor/update-public.pem');self.config=self.root/'source.json';self.check_file=self.root/'check.json'
    def status(self):
        values=[]
        for path in sorted((self.root/'jobs').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
            try:value=json.loads(path.read_text())
            except (ValueError,OSError):continue
            if re.fullmatch('[a-f0-9]{16}',value.get('id','')):self.app.jobs[value['id']]=value;values.append(value)
        return values
    def info(self):
        metadata=self.app.state/'release-state.json';installed=json.loads(metadata.read_text()) if metadata.exists() else {}
        return {'current':self.current,'previous':(installed.get('previous') or {}).get('version'),'trusted_key':self.key.exists(),
            'key_fingerprint':hashlib.sha256(self.key.read_bytes()).hexdigest() if self.key.exists() else None,
            'repository':json.loads(self.config.read_text()).get('repository','') if self.config.exists() else '',
            'check':json.loads(self.check_file.read_text()) if self.check_file.exists() else None,'jobs':self.status(),
            'candidates':[json.loads(p.read_text()) for p in sorted((self.root/'candidates').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:5]]}
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
        if action=='source':
            if not isinstance(data.get('repository',''),str):raise self.error('Use a GitHub owner/repository name.')
            repo=data.get('repository','').strip()
            if repo and not REPO.fullmatch(repo):raise self.error('Use a public GitHub owner/repository name.')
            self.atomic(self.config,{'repository':repo});self.check_file.unlink(missing_ok=True);return {'repository':repo}
        if action=='check':
            repo=json.loads(self.config.read_text()).get('repository','') if self.config.exists() else ''
            if not REPO.fullmatch(repo):raise self.error('Choose a GitHub repository first, or upload a signed update bundle.',409)
            def check():
                self.app.job_progress('Checking GitHub','Reading the latest published release.')
                with github_open('https://api.github.com/repos/'+repo+'/releases/latest') as response:
                    raw=response.read(2*1024**2+1)
                if len(raw)>2*1024**2:raise self.error('The GitHub release metadata is too large.')
                release=json.loads(raw);tag=release.get('tag_name','').removeprefix('v');version(tag)
                if release.get('draft') or release.get('prerelease'):raise self.error('Only published stable releases are supported.')
                name='harbour-'+tag+'-amd64.harbour-update';asset=next((a for a in release.get('assets',[]) if a.get('name')==name),None)
                if not asset:raise self.error('This GitHub release has no Harbour update bundle.')
                url=asset.get('browser_download_url','');parsed=urllib.parse.urlsplit(url)
                if parsed.scheme!='https' or parsed.netloc!='github.com' or not parsed.path.startswith('/'+repo+'/releases/download/') or not 0<asset.get('size',0)<=LIMIT:raise self.error('Invalid GitHub update asset.')
                value={'version':tag,'available':version(tag)>version(self.current),'url':url,'bytes':asset['size'],'checked':datetime.now(timezone.utc).isoformat(),'notes':str(release.get('body',''))[:16000]}
                self.atomic(self.check_file,value);return value
            return self.app.job('Check Harbour releases',check,kind='release')
        if action=='download':
            if not self.key.exists():raise self.error('No trusted release key is installed.',409)
            checked=json.loads(self.check_file.read_text()) if self.check_file.exists() else None
            if not checked or not checked['available']:raise self.error('Check for an available release first.',409)
            def download():
                ident=secrets.token_hex(16);path=self.root/'incoming'/(ident+'.bundle')
                self.app.job_progress('Downloading release','Fetching the GitHub release bundle; it will be verified before installation.')
                try:
                    with github_open(checked['url']) as response,path.open('xb') as output:
                        count=0
                        while chunk:=response.read(1024**2):
                            count+=len(chunk)
                            if count>LIMIT:raise self.error('The release download exceeds 64 MiB.')
                            output.write(chunk)
                    self.app.job_progress('Verifying signature','Checking the pinned signing key and payload checksums.')
                    return self.stage(path,ident)
                except Exception:path.unlink(missing_ok=True);raise
            return self.app.job('Download Harbour update',download,kind='release')
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
