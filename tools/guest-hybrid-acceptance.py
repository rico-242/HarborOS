"""Destructive acceptance exclusively inside the disposable hybrid VM."""
import hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
sys.path[:0]=['/opt/hybrid-code','/opt/harbor']
from storage import StorageManager
from hybrid_storage import atomic_text
class APIError(Exception):
 def __init__(self,message,status=400):super().__init__(message)
def run(*args,timeout=60,check=True):
 result=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if check and result.returncode:raise RuntimeError(str(args)+': '+result.stderr+result.stdout)
 return result
def atomic_json(path,value):atomic_text(path,json.dumps(value,indent=2))
ROOT=Path('/var/lib/harbour-hybrid-acceptance');ROOT.mkdir(exist_ok=True)
if os.environ.get('HYBRID_SANDBOX_TEST'):
 assert 'NoNewPrivs:\t1' in Path('/proc/self/status').read_text()
 properties=subprocess.check_output(['systemctl','show','harbour-hybrid-acceptance','-p','ProtectHome','-p','ProtectKernelTunables','-p','ProtectKernelModules','-p','ProtectControlGroups','-p','NoNewPrivileges','-p','PrivateTmp'],text=True)
 assert all(name+'=yes' in properties for name in ('ProtectHome','ProtectKernelTunables','ProtectKernelModules','ProtectControlGroups','NoNewPrivileges','PrivateTmp')),properties
class App:
 demo=False
 def __init__(self):
  import threading
  self.lock=threading.RLock();self.state=ROOT;self.storage=Path('/srv/harbor/hybrid-acceptance');self.storage.mkdir(parents=True,exist_ok=True)
  self.config=json.loads((ROOT/'config.json').read_text()) if (ROOT/'config.json').exists() else {}
 def save(self):atomic_json(ROOT/'config.json',self.config)
 def sync_samba(self):pass
 def job(self,title,action,**kw):return action()
 def job_progress(self,stage,detail=''):
  (ROOT/'progress.json').write_text(json.dumps({'stage':stage,'detail':detail}));print(stage,detail,flush=True)
 def storage_info(self):
  fs=json.loads(run('findmnt','-J','-T',str(self.storage),'-o','SOURCE,FSTYPE,TARGET').stdout)['filesystems'][0]
  usage=shutil.disk_usage(self.storage);status=self.manager.hybrid_status() if hasattr(self,'manager') else None
  return {'mounted':fs['target']==str(self.storage),'filesystem':fs['fstype'],'source':fs['source'],'total':usage.total,'free':usage.free,'healthy':status['healthy'] if status else True}
app=App();manager=app.manager=StorageManager(app,run,APIError)
def disks(indices):
 inventory=manager.inventory();chosen=[]
 for i in indices:
  item=next(d for d in inventory if d['serial']=='HARBOUR_HYBRID_'+str(i))
  assert re.fullmatch(r'/dev/disk/by-id/virtio-HARBOUR_HYBRID_\d+',item['id']);chosen.append(item)
 return chosen
def create(level,indices):
 values=disks(indices);plan=manager.plan({'name':'Hybrid-Test','level':level,'disks':[d['id'] for d in values]})
 manager.create({'token':plan['token'],'confirmation':plan['confirmation'],'acknowledge':True})
 assert app.storage_info()['mounted'];return values
def wait_sync():
 for _ in range(600):
  status=manager.hybrid_status()
  if status and all(a.get('sync_action')=='idle' for a in status['arrays']):assert status['healthy'];return
  time.sleep(1)
 raise RuntimeError('RAID synchronization did not finish')
def expand(indices):
 values=disks(indices);plan=manager.expand_plan({'disks':[d['id'] for d in values]})
 manager.expand({'token':plan['token'],'confirmation':plan['confirmation'],'acknowledge':True})
 return plan
def digest():return hashlib.sha256((app.storage/'probe.bin').read_bytes()).hexdigest()
def fail(indices):
 ids={d['id'] for d in disks(indices)}
 for group in app.config['storage']['hybrid']['groups']:
  for array in group['arrays']:
   for member in array['members']:
    if member.rsplit('-part',1)[0] in ids:
     run('mdadm',array['path'],'--fail',member);run('mdadm',array['path'],'--remove',member)
 run('sync');assert not manager.hybrid_status()['healthy']
def cleanup():
 unit=run('systemd-escape','--path','--suffix=mount',str(app.storage)).stdout.strip();run('systemctl','stop',unit)
 for group in app.config['storage']['hybrid']['groups']:
  for array in group['arrays']:run('mdadm','--stop',array['path'])
 run('udevadm','settle');app.config={};app.save()
phase=os.environ.get('HYBRID_PHASE','create')
if phase=='create':
 create('hybrid1',[1,2,3,4]);wait_sync()
 (app.storage/'probe.bin').write_bytes(os.urandom(16*1024**2));original=digest();before=app.storage_info()['total']
 expand([5,6]);wait_sync();assert digest()==original and app.storage_info()['total']>before
 fail([1]);assert digest()==original
 run('btrfs','scrub','start','-B',str(app.storage),timeout=180)
 first={'service_sandbox_verified':bool(os.environ.get('HYBRID_SANDBOX_TEST')),'mixed_hybrid1':True,'hybrid1_expansion_retained_data':True,'one_drive_failure_read_and_scrub':True}
 cleanup()
 create('hybrid2',[1,2,3,4,5,6]);wait_sync()
 (app.storage/'probe.bin').write_bytes(os.urandom(16*1024**2));original=digest();before=app.storage_info()['total']
 expand([7,8,9,10]);wait_sync();assert digest()==original and app.storage_info()['total']>before
 atomic_json(ROOT/'expected.json',{'digest':original,'report':dict(first,mixed_hybrid2=True,hybrid2_expansion_retained_data=True)})
 print('READY_FOR_REBOOT',flush=True)
elif phase=='reboot-check':
 expected=json.loads((ROOT/'expected.json').read_text());assert app.storage_info()['mounted'] and digest()==expected['digest'];wait_sync()
 expected['report']['hybrid2_reboot_persistence']=True
 fail([3,4]);assert digest()==expected['digest'];run('btrfs','scrub','start','-B',str(app.storage),timeout=180)
 expected['report']['two_drive_failure_read_and_scrub']=True
 atomic_json(ROOT/'expected.json',expected);print('READY_FOR_DEGRADED_REBOOT',flush=True)
elif phase=='degraded-check':
 expected=json.loads((ROOT/'expected.json').read_text());assert app.storage_info()['mounted'] and digest()==expected['digest']
 assert not manager.hybrid_status()['healthy'];expected['report']['degraded_reboot_persistence']=True
 atomic_json(ROOT/'result.json',expected['report']);print(json.dumps(expected['report']),flush=True)
elif phase=='native':
 expected=json.loads((ROOT/'expected.json').read_text());cleanup()
 # Remove old signatures only from the ten whitelisted disposable disks.
 values=disks(list(range(1,11)))
 parts=manager.array_preflight(values)
 for partition in parts:run('wipefs','--all',partition)
 for disk in values:run('wipefs','--all',disk['id'])
 ids=[d['id'] for d in disks([1,2])]
 run('mkfs.btrfs','-f','-d','raid1','-m','raid1',*ids)
 uuid=run('blkid','-s','UUID','-o','value',ids[0]).stdout.strip()
 fstab=Path('/etc/fstab');lines=[line for line in fstab.read_text().splitlines() if len(line.split())<2 or line.split()[1]!=str(app.storage)]
 lines.append(f'UUID={uuid} {app.storage} btrfs defaults,nofail,x-systemd.device-timeout=30 0 0');atomic_text(fstab,'\n'.join(lines)+'\n')
 run('systemctl','daemon-reload');unit=run('systemd-escape','--path','--suffix=mount',str(app.storage)).stdout.strip();run('systemctl','start',unit)
 app.config={'storage':{'name':'Native-Test','level':'native-raid1','uuid':uuid,'disks':ids}};app.save()
 (app.storage/'probe.bin').write_bytes(os.urandom(16*1024**2));original=digest();before=app.storage_info()['total']
 expand([3]);assert digest()==original and app.storage_info()['total']>before
 usage=run('btrfs','filesystem','usage','-b',str(app.storage)).stdout
 assert 'Data,RAID1:' in usage and 'Metadata,RAID1:' in usage
 expected['digest']=original;expected['report']['native_raid1_expansion_retained_data_and_profiles']=True
 atomic_json(ROOT/'expected.json',expected);print('READY_FOR_NATIVE_REBOOT',flush=True)
elif phase=='native-reboot':
 expected=json.loads((ROOT/'expected.json').read_text());expected['report'].update(json.loads((ROOT/'result.json').read_text()));assert app.storage_info()['mounted'] and digest()==expected['digest']
 expected['report']['native_raid1_expansion_reboot_persistence']=True
 atomic_json(ROOT/'result.json',expected['report']);print(json.dumps(expected['report']),flush=True)
else:raise RuntimeError('Unknown acceptance phase')
