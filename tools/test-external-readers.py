#!/usr/bin/env python3
"""Read-only filesystem acceptance using disposable loop images only; no real disks."""
import errno,json,os,shutil,subprocess,sys,tempfile,threading
from pathlib import Path
assert os.geteuid()==0,'Run as root in a disposable VM or explicit loop-image test.'
assert os.getenv('HARBOUR_EXTERNAL_LOOP_TEST')=='1','Explicit loop-test opt-in required.'
repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo/'harbor') if (repo/'harbor').is_dir() else '/opt/harbor')
from externaldrives import ExternalDrives
from types import SimpleNamespace
class Error(Exception):
 def __init__(self,message,status=400):super().__init__(message)
def command(*args,**kwargs):return subprocess.run(args,text=True,capture_output=True,check=kwargs.get('check',True),timeout=kwargs.get('timeout',60))
results={}
with tempfile.TemporaryDirectory(prefix='harbour-filesystem-test-',dir='/run') as folder:
 root=Path(folder);state=root/'state';state.mkdir();rw=root/'prepare';rw.mkdir()
 app=SimpleNamespace(demo=False,state=state,config={},jobs={},lock=threading.RLock())
 manager=ExternalDrives(app,command,Error);manager.root=root/'mounts'
 for fs,size,mkfs in [('ext4',64,['mkfs.ext4','-F','-q']),('vfat',64,['mkfs.vfat']),('exfat',64,['mkfs.exfat']),('ntfs',64,['mkfs.ntfs','-F','-Q']),('btrfs',128,['mkfs.btrfs','-f','-q']),('xfs',512,['mkfs.xfs','-f','-q']),('f2fs',128,['mkfs.f2fs','-f','-q'])]:
  image=root/(fs+'.img');image.touch();os.truncate(image,size*1024**2)
  loop=command('losetup','--find','--show',str(image)).stdout.strip()
  assert loop.startswith('/dev/loop') and Path(loop).is_block_device()
  ident=('test-'+fs).encode().hex()[:24].ljust(24,'0');target=manager.root/ident
  try:
   command(*mkfs,loop)
   command('mount','-t','ntfs-3g' if fs=='ntfs' else fs,loop,str(rw))
   try:(rw/'harbour-test.txt').write_text('Harbour read-only acceptance\n')
   finally:command('umount',str(rw))
   disk=dict(id=ident,device=loop,path=loop,serial='DISPOSABLE-LOOP',filesystem=fs,uuid=fs,label=fs,size=size*1024**2,eligible=True,reason='',mounted=False)
   manager.inventory=lambda d=disk:[dict(d,mounted=ident in manager.mounted)]
   manager.action(dict(action='mount',id=ident))
   assert manager.path(ident,'harbour-test.txt').read_text()=='Harbour read-only acceptance\n'
   assert any(e['name']=='harbour-test.txt' for e in manager.files(ident,'')['entries'])
   try:(target/'must-not-write.txt').write_text('no')
   except OSError as error:assert error.errno in (errno.EROFS,errno.EACCES),error
   else:raise AssertionError('Read-only mount allowed a write')
   manager.action(dict(action='unmount',id=ident));results[fs]=True
  finally:
   for mount in (target,rw):
    if mount.is_mount():command('umount',str(mount))
   command('losetup','--detach',loop);image.unlink(missing_ok=True)
print(json.dumps(dict(disposable_loop_images_only=True,readonly_readers=results)))
