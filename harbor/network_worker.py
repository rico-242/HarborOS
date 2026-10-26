"""Root network transaction worker. Called by fixed systemd units, never a shell."""
import fcntl,json,os,re,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from networking import configuration

ROOT=Path('/var/lib/harbor/network');NETWORK=Path('/etc/systemd/network')
def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.new')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    temporary.replace(path);directory=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(directory)
    finally:os.close(directory)
def run(*args,check=True):return subprocess.run(args,capture_output=True,text=True,check=check,timeout=35)
def managed():return [*NETWORK.glob('04-harbour-port-*.network'),NETWORK/'05-harbour-bond.network',NETWORK/'05-harbour-bond.netdev']
def load():return json.loads((ROOT/'status.json').read_text())
def save(state,stage=None):
    if stage:
        state['stage']=stage;state['steps']=(state.get('steps',[])+[{'stage':stage,'detail':'','time':datetime.now(timezone.utc).isoformat()}])[-20:]
    atomic(ROOT/'status.json',state)
def restore(state,boot=False):
    folder=ROOT/'transactions'/state['id'];backup=json.loads((folder/'backup.json').read_text())
    for path in managed():
        if path.is_symlink():raise RuntimeError('Refusing to replace a linked network configuration')
        path.unlink(missing_ok=True)
    for name,content in backup['files'].items():(NETWORK/name).write_text(content)
    if backup['config'] is None:(ROOT/'config.json').unlink(missing_ok=True)
    else:atomic(ROOT/'config.json',backup['config'])
    if not boot:
        for port in state['interfaces']:run('ip','link','set','dev',port,'nomaster',check=False)
        run('ip','link','delete','bond0',check=False)
        run('networkctl','reload')
        for port in state['interfaces']:run('networkctl','reconfigure',port,check=False)
        if backup['config'] is not None:run('networkctl','reconfigure','bond0',check=False)
    os.sync()
    state.update(state='completed',phase='rolled_back',finished=datetime.now(timezone.utc).isoformat(),detail='The previous network configuration was restored.')
    save(state,'Previous network restored')

def main(action,ident=None):
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    with Path('/run/harbour-network.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if action=='recover':
            if (ROOT/'status.json').exists():
                state=load()
                if state.get('phase') in ('applying','awaiting_confirmation'):restore(state,boot=True)
            return
        if not ident or not re.fullmatch('[a-f0-9]{16}',ident):raise ValueError('Invalid transaction identity')
        state=load()
        if state['id']!=ident:return
        if action in ('keep','revert','timeout'):
            if state.get('phase') not in ('applying','awaiting_confirmation'):return
            if action=='keep':
                if state.get('phase')!='awaiting_confirmation':raise RuntimeError('The network change is still applying')
                if time.time()>=state['deadline']:restore(state);raise RuntimeError('The confirmation period expired; previous settings were restored')
                request=json.loads((ROOT/'request.json').read_text())
                if request['action']=='apply':atomic(ROOT/'config.json',request['plan'])
                else:(ROOT/'config.json').unlink(missing_ok=True)
                state.update(state='completed',phase='confirmed',finished=datetime.now(timezone.utc).isoformat(),detail='The network configuration was confirmed and saved.');save(state,'Network change saved')
            else:restore(state)
            return
        if action!='apply':raise ValueError('Unknown network operation')
        with Path('/run/harbour-maintenance.lock').open('w') as maintenance:
            fcntl.flock(maintenance,fcntl.LOCK_EX|fcntl.LOCK_NB)
            request=json.loads((ROOT/'request.json').read_text());assert request['id']==ident
            plan=request['plan'];state.update(state='running',phase='applying',started=datetime.now(timezone.utc).isoformat(),interfaces=[i['name'] for i in plan['interfaces']])
            folder=ROOT/'transactions'/ident;folder.mkdir(mode=0o700,parents=True,exist_ok=False)
            files={}
            for path in managed():
                if path.is_symlink():raise RuntimeError('Refusing to replace a linked network file')
                if path.exists():files[path.name]=path.read_text()
            previous=json.loads((ROOT/'config.json').read_text()) if (ROOT/'config.json').exists() else None
            if previous is None and files:raise RuntimeError('Reserved Harbour network files already exist without an ownership record')
            atomic(folder/'backup.json',{'files':files,'config':previous})
            save(state,'Saving previous network')
            try:
                run('modprobe','bonding')
                # The timer exists before any configuration file or interface is changed.
                deadline=time.time()+120
                run('systemd-run','--collect','--on-active=120s','--unit=harbour-network-revert-'+ident,'/usr/local/sbin/harbour-network-change','timeout',ident)
                for path in managed():path.unlink(missing_ok=True)
                if request['action']=='apply':
                    for name,content in configuration(plan).items():(NETWORK/name).write_text(content)
                os.sync()
                save(state,'Applying network configuration')
                if request['action']=='remove':
                    for port in state['interfaces']:run('ip','link','set','dev',port,'nomaster',check=False)
                    run('ip','link','delete','bond0')
                run('networkctl','reload')
                for port in state['interfaces']:run('networkctl','reconfigure',port)
                if request['action']=='apply':
                    for _ in range(15):
                        if Path('/sys/class/net/bond0').exists():break
                        time.sleep(.2)
                    run('networkctl','reconfigure','bond0')
                # Timer started before reconfiguration, so use its remaining confirmation window.
                state.update(phase='awaiting_confirmation',deadline=deadline,detail='Reconnect and confirm this connection. Otherwise the previous network settings return automatically.')
                save(state,'Confirm the new connection')
            except Exception as error:
                try:
                    restore(state)
                    state.update(state='failed',phase='failed',error=str(error),finished=datetime.now(timezone.utc).isoformat());save(state,'Network change stopped')
                except Exception as recovery:
                    state.update(state='failed',phase='applying',error=str(error)+' Recovery pending: '+str(recovery));save(state,'Network recovery required')
                raise

def record_failure(ident,error):
    if not (ROOT/'status.json').exists():return
    state=load()
    if state.get('id')!=ident or state.get('state') not in ('queued','running'):return
    state.update(state='failed',error=str(error))
    if state.get('phase')=='queued':state['phase']='failed'
    save(state,'Network change stopped')

if __name__=='__main__':
    os.umask(0o077)
    try:main(*sys.argv[1:])
    except Exception as error:
        print(str(error),file=sys.stderr);sys.exit(1)
