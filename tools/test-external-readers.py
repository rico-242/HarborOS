#!/usr/bin/env python3
"""Read/write filesystem acceptance using disposable loop images only; no real disks."""
import errno,io,json,os,shutil,subprocess,sys,tempfile,threading
from pathlib import Path
assert os.geteuid()==0,'Run as root in a disposable VM or explicit loop-image test.'
assert os.getenv('HARBOUR_EXTERNAL_LOOP_TEST')=='1','Explicit loop-test opt-in required.'
repo=Path(__file__).resolve().parents[1]
if (repo/'harbor').is_dir():sys.path.insert(0,str(repo/'harbor'))
else:sys.path.append('/opt/harbor')
from externaldrives import ExternalDrives
from types import SimpleNamespace
class Error(Exception):
 def __init__(self,message,status=400):super().__init__(message)
def command(*args,**kwargs):return subprocess.run(args,text=True,capture_output=True,check=kwargs.get('check',True),timeout=kwargs.get('timeout',60))
results={}
with tempfile.TemporaryDirectory(prefix='harbour-filesystem-test-',dir='/run') as folder:
 root=Path(folder);state=root/'state';state.mkdir();rw=root/'prepare';rw.mkdir()
 app=SimpleNamespace(demo=False,state=state,admin={'username':'nobody'},config={},jobs={},lock=threading.RLock())
 manager=ExternalDrives(app,command,Error);manager.root=root/'mounts'
 for fs,size,mkfs in [('ext2',64,['mkfs.ext2','-F','-q']),('ext3',64,['mkfs.ext3','-F','-q']),('ext4',64,['mkfs.ext4','-F','-q']),('vfat',64,['mkfs.vfat']),('exfat',64,['mkfs.exfat']),('ntfs',64,['mkfs.ntfs','-F','-Q']),('btrfs',128,['mkfs.btrfs','-f','-q']),('xfs',512,['mkfs.xfs','-f','-q']),('f2fs',128,['mkfs.f2fs','-f','-q'])]:
  print('Testing '+fs,file=sys.stderr,flush=True)
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
   try:manager.action(dict(action='mount',id=ident,mode='rw',acknowledge=True,confirmation='wrong'))
   except Error:pass
   else:raise AssertionError('Writing did not require exact disk confirmation')
   manager.action(dict(action='mount',id=ident,mode='rw',acknowledge=True,confirmation=manager.write_confirmation(disk)))
   assert not manager.files(ident,'')['readonly']
   manager.file_action(dict(id=ident,operation='mkdir',path='',name='Import'))
   manager.upload(ident,'Import','first.txt',io.BytesIO(b'uploaded content'),16)
   manager.upload(ident,'Import','occupied.txt',io.BytesIO(b'keep'),4)
   try:manager.file_action(dict(id=ident,operation='rename',path='Import/first.txt',name='occupied.txt'))
   except Error:pass
   else:raise AssertionError('Rename overwrote an existing file')
   assert manager.path(ident,'Import/occupied.txt').read_bytes()==b'keep'
   if fs in {'ext2','ext3','ext4','btrfs','xfs','f2fs'}:
    import pwd
    assert (target/'Import/first.txt').stat().st_uid==pwd.getpwnam('nobody').pw_uid
   manager.file_action(dict(id=ident,operation='rename',path='Import/first.txt',name='renamed.txt'))
   assert manager.path(ident,'Import/renamed.txt').read_bytes()==b'uploaded content'
   try:manager.upload(ident,'Import','renamed.txt',io.BytesIO(b'replace'),7)
   except Error:pass
   else:raise AssertionError('Upload overwrote an existing file')
   try:manager.upload(ident,'Import','interrupted.txt',io.BytesIO(b'x'),5)
   except Error:pass
   else:raise AssertionError('Incomplete upload accepted')
   assert not (target/'Import/interrupted.txt').exists()
   assert not list((target/'Import').glob('.harbour-upload-*'))
   try:manager.file_action(dict(id=ident,operation='delete',path='Import',confirmation='wrong'))
   except Error:pass
   else:raise AssertionError('Delete did not require exact item confirmation')
   manager.file_action(dict(id=ident,operation='mkdir',path='',name='Taken'))
   try:manager.file_action(dict(id=ident,operation='rename',path='Import',name='Taken'))
   except Error:pass
   else:raise AssertionError('Rename replaced an existing directory')
   outside=root/'outside';outside.mkdir(exist_ok=True);(outside/'keep.txt').write_text('untouched')
   try:os.symlink(outside,target/'Import/escape')
   except OSError as error:assert error.errno in (errno.EPERM,errno.EOPNOTSUPP,errno.EACCES,errno.ENOSYS),error
   else:
    try:manager.file_action(dict(id=ident,operation='mkdir',path='Import/escape',name='must-not-create'))
    except Error:pass
    else:raise AssertionError('Write followed a symbolic link outside the disk')
   manager.file_action(dict(id=ident,operation='rename',path='Import',name='Finished'))
   manager.file_action(dict(id=ident,operation='delete',path='Finished',confirmation='DELETE Finished'))
   assert not (target/'Finished').exists()
   assert (outside/'keep.txt').read_text()=='untouched'
   assert not (outside/'must-not-create').exists()
   manager.upload(ident,'','persistent.txt',io.BytesIO(b'persistent write'),16)
   manager.action(dict(action='mount',id=ident,mode='ro'))
   assert manager.files(ident,'')['readonly']
   assert manager.path(ident,'persistent.txt').read_bytes()==b'persistent write'
   try:manager.upload(ident,'','blocked.txt',io.BytesIO(b'no'),2)
   except Error:pass
   else:raise AssertionError('Upload bypassed read-only mode')
   manager.action(dict(action='unmount',id=ident))
   manager.action(dict(action='mount',id=ident))
   assert manager.path(ident,'persistent.txt').read_bytes()==b'persistent write'
   manager.action(dict(action='unmount',id=ident));results[fs]=True
  finally:
   for mount in (target,rw):
    if mount.is_mount():command('umount',str(mount))
   command('losetup','--detach',loop);image.unlink(missing_ok=True)
print(json.dumps(dict(disposable_loop_images_only=True,readonly_readers=results,readwrite_readers=results)))
