"""Destructive acceptance test restricted to two sparse-file loops inside QEMU live RAM."""
import json,os,subprocess,tempfile,threading
from pathlib import Path
from types import SimpleNamespace
assert os.geteuid()==0
assert 'Standard PC' in Path('/sys/class/dmi/id/product_name').read_text()
assert 'boot=live' in Path('/proc/cmdline').read_text().split()
from storage import StorageManager
class WipeTestError(Exception):
 def __init__(self,message,status=400):super().__init__(message)
with tempfile.TemporaryDirectory(prefix='harbour-wipe-',dir='/run') as folder:
 root=Path(folder);loops=[];alias=Path('/dev/disk/by-id')/root.name;array='/dev/md/'+root.name
 def raw(*args,**kw):return subprocess.run(args,text=True,capture_output=True,check=True,**kw)
 try:
  for i in range(2):
   image=root/('disk'+str(i)+'.img')
   with image.open('wb') as stream:stream.truncate(96*1024**2)
   loops.append(raw('losetup','--find','--show','--partscan',str(image)).stdout.strip())
  # Verify ownership of every loop before creating the disposable array.
  for loop in loops:
   backing=raw('losetup','--noheadings','--output','BACK-FILE',loop).stdout.strip()
   assert Path(backing).parent==root
  alias.parent.mkdir(parents=True,exist_ok=True);assert not alias.exists();alias.symlink_to(loops[0])
  raw('mdadm','--create',array,'--metadata=1.2','--name='+root.name,'--level=1','--raid-devices=2','--assume-clean','--run',*loops)
  raw('udevadm','settle')
  disk=dict(id=str(alias),path=loops[0],size=96*1024**2,serial=root.name,wwn='',model='Disposable VM loop',eligible=False,reason='Old unused array',existing_data=True)
  def command(*args,**kw):
   # Never accept any write outside the two loops and the fixture array.
   if args[0] in ('mdadm','wipefs','blockdev'):
    for value in args:
     if value.startswith('/dev/'):assert value in (*loops,str(alias),array) or Path(value).resolve()==Path(array).resolve()
   try:result=subprocess.run(args,text=True,capture_output=True,check=kw.get('check',True),timeout=kw.get('timeout',30))
   except subprocess.CalledProcessError as error:raise RuntimeError(str(error)+': '+error.stderr.strip()) from None
   if args[0]=='lsblk':
    data=json.loads(result.stdout)
    def translate(items):
     for item in items:
      if item.get('type')=='loop':assert item['path'] in loops;item['type']='disk'
      translate(item.get('children',[]))
    translate(data['blockdevices']);result.stdout=json.dumps(data)
   return result
  app=SimpleNamespace(demo=False,state=root,config={'storage':{'disks':[loops[1]]}},lock=threading.RLock(),job=lambda title,fn,**kw:fn(),job_progress=lambda *args:None,event=lambda *args:None)
  manager=StorageManager(app,command,WipeTestError);manager.inventory=lambda:[disk]
  try:manager.wipe_plan({'disk':str(alias)});raise AssertionError('Another current pool member on the same array was not protected')
  except WipeTestError as error:assert 'pool' in str(error)
  # Keep the fixture's members attached while stopping its personality.
  # `mdadm --assemble` may remove the incomplete device again on exit.
  resolved_array=Path(array).resolve();sys_array=Path('/sys/class/block')/resolved_array.name
  assert {item.name for item in (sys_array/'slaves').glob('*')}=={Path(loop).name for loop in loops}
  (sys_array/'md/array_state').write_text('inactive\n')
  array=str(resolved_array)
  raw('udevadm','settle')
  topology=json.loads(raw('lsblk','-J','-b','-p','-o','PATH,TYPE,SIZE',array).stdout)
  assert (sys_array/'md/array_state').read_text().strip()=='inactive'
  assert topology['blockdevices'][0]['type'] in ('md','raid1') and topology['blockdevices'][0]['size']==0,topology
  app.config={'storage':{}}
  def no_health(*args):raise AssertionError('Wiping must not depend on SMART health')
  manager.health=no_health
  plan=manager.wipe_plan({'disk':str(alias)})
  result=manager.wipe_disk({'token':plan['token'],'confirmation':plan['confirmation'],'acknowledge':True})
  assert result['wiped'] and not manager.pending().exists()
  assert not json.loads(raw('wipefs','--json',loops[0]).stdout)['signatures']
  assert 'MD_UUID=' in raw('mdadm','--examine','--export',loops[1]).stdout
 finally:
  # Only detach arrays whose every slave is one of this fixture's file loops.
  for loop in loops:
   for holder in (Path('/sys/class/block')/Path(loop).name/'holders').glob('*'):
    slaves={p.name for p in (holder/'slaves').glob('*')}
    assert slaves and slaves<={Path(p).name for p in loops}
    subprocess.run(['mdadm','--stop','/dev/'+holder.name],check=True,capture_output=True)
  alias.unlink(missing_ok=True)
  for loop in reversed(loops):raw('losetup','--detach',loop)
