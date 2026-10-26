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

cleanup()
values=disks(list(range(1,11)));parts=manager.array_preflight(values)
for part in parts:run('wipefs','--all',part)
for disk in values:run('wipefs','--all',disk['id'])
create('hybrid1',[1,2,3,4]);wait_sync();(app.storage/'probe.bin').write_bytes(os.urandom(16*1024**2));original=digest()
p=manager.lifecycle_plan({'operation':'replace','member':disks([3])[0]['id'],'target':disks([5])[0]['id']})
manager.lifecycle_action({'token':p['token'],'confirmation':p['confirmation'],'acknowledge':True})
assert manager.hybrid_status()['healthy'] and digest()==original
p=manager.lifecycle_plan({'operation':'remove','member':disks([2])[0]['id']})
manager.lifecycle_action({'token':p['token'],'confirmation':p['confirmation'],'acknowledge':True})
p=manager.lifecycle_plan({'operation':'replace','member':disks([2])[0]['id'],'target':disks([6])[0]['id']})
manager.lifecycle_action({'token':p['token'],'confirmation':p['confirmation'],'acknowledge':True})
assert manager.hybrid_status()['healthy'] and digest()==original
report=json.loads((ROOT/'lifecycle-result.json').read_text());report['hybrid1_multi_tier_replacement']=True;report['hybrid1_detach_repair']=True
atomic_json(ROOT/'lifecycle-result.json',report)
cleanup()
values=disks(list(range(1,11)));parts=manager.array_preflight(values)
for part in parts:run('wipefs','--all',part)
for disk in values:run('wipefs','--all',disk['id'])
create('1',[1,2])
for _ in range(120):
 md=Path('/sys/class/block')/Path('/dev/md/harbor-data').resolve().name/'md'
 if (md/'sync_action').read_text().strip()=='idle':break
 time.sleep(1)
(app.storage/'probe.bin').write_bytes(os.urandom(16*1024**2));original=digest()
p=manager.lifecycle_plan({'operation':'replace','member':disks([1])[0]['id'],'target':disks([3])[0]['id']})
manager.lifecycle_action({'token':p['token'],'confirmation':p['confirmation'],'acknowledge':True})
assert digest()==original and not any(m['missing'] for m in manager.lifecycle_state()['members'])
report['standard_md_mirror_replacement']=True;atomic_json(ROOT/'lifecycle-result.json',report);atomic_json(ROOT/'lifecycle-hash.json',{'hash':original})
print('HYBRID1_AND_STANDARD_MD_PASSED')
