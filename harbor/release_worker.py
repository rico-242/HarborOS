"""Independent updater core, installed outside the replaceable web application."""
import ast,fcntl,json,os,shutil,subprocess,sys,time,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from release_bundle import HELPERS,inspect_bundle,unpack_verified,version

STATE=Path('/var/lib/harbor');ROOT=STATE/'release-updates';RELEASES=Path('/opt/harbour-releases');APP=Path('/opt/harbor');KEY=Path('/etc/harbor/update-public.pem')
def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.new')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    temp.replace(path);directory=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(directory)
    finally:os.close(directory)
def run(*args,check=True):return subprocess.run(args,capture_output=True,text=True,check=check,timeout=90)
def current_version():
    tree=ast.parse((APP/'server.py').read_text())
    return next(n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in n.targets))
def point(path):
    path=Path(path)
    if not path.is_relative_to(RELEASES) or not path.is_dir():raise RuntimeError('Invalid application release directory')
    temporary=APP.with_name('.harbor-next');temporary.unlink(missing_ok=True);temporary.symlink_to(path,target_is_directory=True);os.replace(temporary,APP)
def helpers_backup(folder):
    folder.mkdir(mode=0o700,parents=True,exist_ok=True);records={}
    for name,target in HELPERS.items():
        path=Path(target);records[name]={'exists':path.exists(),'mode':path.stat().st_mode&0o777 if path.exists() else 0o755}
        if path.exists():shutil.copyfile(path,folder/name)
    atomic(folder/'record.json',records)
def helpers_restore(folder):
    folder=Path(folder);records=json.loads((folder/'record.json').read_text())
    for name,record in records.items():
        target=Path(HELPERS[name]);target.parent.mkdir(parents=True,exist_ok=True)
        if not record['exists']:target.unlink(missing_ok=True);continue
        temp=target.with_name('.'+target.name+'.update');shutil.copyfile(folder/name,temp);temp.chmod(record['mode']);os.replace(temp,target)
def restore(journal):
    old=Path(journal['old_path'])
    if old.exists():point(old)
    elif APP.is_symlink() or not APP.is_dir():raise RuntimeError('The previous application release could not be restored')
    helpers_restore(journal['helper_backup'])
    if 'old_os_release' in journal:Path('/etc/os-release').write_text(journal['old_os_release'])
    if journal['old_metadata'] is None:(STATE/'release-state.json').unlink(missing_ok=True)
    else:atomic(STATE/'release-state.json',journal['old_metadata'])
    os.sync();journal['phase']='restored';atomic(ROOT/'activation.json',journal)
def recover():
    path=ROOT/'activation.json'
    if path.exists():
        journal=json.loads(path.read_text())
        if journal['phase']=='activating':restore(journal)
    # Jobs from a previous boot cannot still be running. Clear them so an
    # interrupted download/activation cannot permanently block maintenance.
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    for file in (ROOT/'jobs').glob('*.json'):
        value=json.loads(file.read_text())
        if value.get('state') in ('queued','running') and value.get('boot_id')!=boot:
            value.update(state='failed',stage='Interrupted update recovered',error='The appliance restarted during this update. The previous release is available.',finished=datetime.now(timezone.utc).isoformat());atomic(file,value)
def execute(ident):
    import re
    if not re.fullmatch('[a-f0-9]{16}',ident):raise ValueError('Invalid release job identity')
    request=json.loads((ROOT/'requests'/(ident+'.json')).read_text());job=request['job'];file=ROOT/'jobs'/(ident+'.json')
    def report(stage,detail='',state='running',**extra):
        job['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        job.update(state=state,stage=stage,detail=detail,**extra);job.setdefault('started',datetime.now(timezone.utc).isoformat());job['steps']=(job.get('steps',[])+[{'stage':stage,'detail':detail,'time':datetime.now(timezone.utc).isoformat()}])[-30:];atomic(file,job)
    journal=None
    try:
        with Path('/run/harbour-maintenance.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            network=STATE/'network/status.json'
            if network.exists() and json.loads(network.read_text()).get('phase') in ('applying','awaiting_confirmation'):raise RuntimeError('Confirm or revert the pending network change first')
            report('Verifying release','Checking the trusted signing key, checksums, version and supported platform.')
            installed=current_version();meta_path=STATE/'release-state.json';old_metadata=json.loads(meta_path.read_text()) if meta_path.exists() else None
            import platform
            os_release=Path('/etc/os-release').read_text()
            if platform.machine().lower() not in ('x86_64','amd64') or 'ID=harbor' not in os_release or 'DEBIAN_CODENAME=trixie' not in os_release:raise RuntimeError('This updater supports Harbour on Debian 13 amd64 only')
            RELEASES.mkdir(mode=0o755,exist_ok=True);transaction=ROOT/'transactions'/ident;transaction.mkdir(mode=0o700,parents=True,exist_ok=False)
            helpers_backup(transaction/'helpers')
            if request['action']=='install':
                bundle=ROOT/'incoming'/request['candidate'];manifest,payload=inspect_bundle(bundle,KEY,installed)
                target_version=manifest['version'];stage=RELEASES/('.stage-'+ident);unpack_verified(manifest,payload,stage)
                for path in (stage/'app').rglob('*.py'):compile(path.read_bytes(),str(path),'exec')
                if shutil.disk_usage(RELEASES).free<256*1024**2:raise RuntimeError('Free at least 256 MiB on the system disk before updating')
                new_path=RELEASES/(target_version+'-'+ident);(stage/'app').rename(new_path)
            elif request['action']=='rollback':
                previous=(old_metadata or {}).get('previous')
                if not previous:raise RuntimeError('There is no previous Harbour release to restore')
                new_path=Path(previous['path']);target_version=previous['version'];version(target_version);stage=None
                if not new_path.is_dir() or not new_path.is_relative_to(RELEASES):raise RuntimeError('The previous application is unavailable')
            else:raise RuntimeError('Unknown release operation')
            old_path=APP.resolve() if APP.is_symlink() else RELEASES/(installed+'-bootstrap-'+ident)
            journal={'phase':'activating','id':ident,'old_path':str(old_path),'old_metadata':old_metadata,'helper_backup':str(transaction/'helpers'),'old_os_release':Path('/etc/os-release').read_text()}
            # Recovery stays active through the subsequent service restart.
            run('systemctl','start','harbour-update-recover.service')
            os.sync()
            atomic(ROOT/'activation.json',journal)
            report('Saving current release','Saving the application and helper files for automatic recovery.')
            run('systemctl','stop','harbor')
            if not APP.is_symlink():APP.rename(old_path)
            if request['action']=='install':
                for name,target in HELPERS.items():
                    source=stage/'helpers'/name
                    if source.exists():
                        dest=Path(target);dest.parent.mkdir(parents=True,exist_ok=True);temp=dest.with_name('.'+dest.name+'.update');shutil.copyfile(source,temp);temp.chmod(0o755);os.replace(temp,dest)
            else:helpers_restore(previous['helpers'])
            point(new_path);os.sync();run('systemctl','daemon-reload')
            report('Starting the new release','The web console will reconnect after its service restarts.')
            run('systemctl','start','harbor')
            expected_setup=not (STATE/'admin.json').exists();healthy=False
            for _ in range(45):
                try:
                    health=json.load(urllib.request.urlopen('http://127.0.0.1:17080/api/health',timeout=2))
                    if health.get('version')==target_version and health.get('setup_required')==expected_setup:healthy=True;break
                except Exception:pass
                time.sleep(1)
            if not healthy:raise RuntimeError('The updated web console did not pass its health check')
            metadata={'version':target_version,'path':str(new_path),'previous':{'version':installed,'path':str(old_path),'helpers':str(transaction/'helpers')},'updated':datetime.now(timezone.utc).isoformat()}
            atomic(meta_path,metadata)
            os_release=Path('/etc/os-release');text=os_release.read_text()
            if '\nID=harbor\n' in '\n'+text:
                import re
                text=re.sub(r'^VERSION="[^"]*"', 'VERSION="'+target_version+'"',text,flags=re.M)
                text=re.sub(r'^VERSION_ID="[^"]*"', 'VERSION_ID="'+target_version+'"',text,flags=re.M)
                text=re.sub(r'^PRETTY_NAME="[^"]*"', 'PRETTY_NAME="Harbour OS '+target_version+' (Debian 13)"',text,flags=re.M);os_release.write_text(text)
            journal['phase']='committed';atomic(ROOT/'activation.json',journal)
            report('Complete','Harbour '+target_version+' is running. Your accounts, apps and data were preserved.',state='completed',finished=datetime.now(timezone.utc).isoformat(),result={'version':target_version})
    except Exception as error:
        detail=str(error)
        if journal and journal['phase']=='activating':
            try:
                run('systemctl','stop','harbor',check=False);restore(journal);run('systemctl','daemon-reload');run('systemctl','start','harbor');detail+=' The previous release was restored.'
            except Exception as recovery:detail+=' Recovery requires attention: '+str(recovery)
        report('Update stopped',detail,state='failed',error=detail,finished=datetime.now(timezone.utc).isoformat());raise

if __name__=='__main__':
    os.umask(0o077)
    try:recover() if sys.argv[1]=='recover' else execute(sys.argv[1])
    except Exception as error:print(str(error),file=sys.stderr);sys.exit(1)
