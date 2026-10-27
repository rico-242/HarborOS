"""Explicit, owner-only, read-only mounts of standalone connected filesystems."""
import hashlib,json,os,re,shutil
from pathlib import Path

FORMATS={'ext2':'ro,nosuid,nodev,noexec','ext3':'ro,noload,nosuid,nodev,noexec','ext4':'ro,noload,nosuid,nodev,noexec','btrfs':'ro,nologreplay,nosuid,nodev,noexec','xfs':'ro,norecovery,nosuid,nodev,noexec','vfat':'ro,nosuid,nodev,noexec','exfat':'ro,nosuid,nodev,noexec','ntfs':'ro,norecover,nosuid,nodev,noexec','hfs':'ro,nosuid,nodev,noexec','hfsplus':'ro,nosuid,nodev,noexec','f2fs':'ro,norecovery,nosuid,nodev,noexec','udf':'ro,nosuid,nodev,noexec','iso9660':'ro,nosuid,nodev,noexec','apfs':'ro,nosuid,nodev,noexec'}
PACKAGES=['ntfs-3g','exfatprogs','xfsprogs','f2fs-tools','udftools','hfsplus','libfsapfs-utils']

class ExternalDrives:
 def __init__(self,app,run,error):
  self.app,self.run,self.error=app,run,error
  self.root=Path('/run/harbor/external') if not app.demo else app.state/'external'
  self.mounted={}
  self.record=app.state/'external-mounts.json'
  if self.record.exists():
   try:
    saved=json.loads(self.record.read_text())
    for key,value in saved.items():
     if re.fullmatch(r'[a-f0-9]{24}',key) and isinstance(value,dict) and str(value.get('device','')).startswith('/dev/disk/by-id/'):
      self.mounted[key]=dict(value,mount=self.root/key)
   except (ValueError,OSError,AttributeError):pass
 def save(self):
  from server import atomic_json
  atomic_json(self.record,{key:{k:v for k,v in value.items() if k!='mount'} for key,value in self.mounted.items()})
 def support(self):
  return dict(formats=list(FORMATS),packages=PACKAGES,missing=[name for name in ('ntfs-3g','fsapfsmount') if not shutil.which(name)],note='Read-only standalone disks. APFS is experimental; encrypted disks, ZFS pools and RAID member partitions require a separate import/unlock workflow.')
 def inventory(self):
  if self.app.demo:return []
  tree=json.loads(self.run('lsblk','--tree','-J','-b','-p','-o','PATH,SIZE,TYPE,FSTYPE,UUID,LABEL,MOUNTPOINTS,SERIAL,MODEL').stdout)['blockdevices']
  result=[]
  def nodes(node):
   yield node
   for child in node.get('children',[]):yield from nodes(child)
  links={str(p.resolve()):str(p) for p in sorted(Path('/dev/disk/by-id').glob('*'),reverse=True)}
  recorded={str(Path(p).resolve()) for p in self.app.config.get('storage',{}).get('disks',[])}
  for disk in tree:
   if disk.get('type') not in ('disk','rom'):continue
   family=list(nodes(disk));system=any(set(n.get('mountpoints') or [])&{'/','/boot','/boot/efi'} for n in family)
   if system:continue
   held=any(any((Path('/sys/class/block')/Path(n['path']).name/'holders').glob('*')) for n in family)
   for node in family:
    fs=node.get('fstype')
    if not fs:continue
    stable=links.get(node['path']);key=hashlib.sha256((str(stable)+str(node.get('uuid'))+str(disk.get('serial'))).encode()).hexdigest()[:24]
    entry=self.mounted.get(key)
    own=bool(entry and self.is_mounted(entry))
    busy=any(m and (not own or m!=str(entry['mount'])) for n in family for m in (n.get('mountpoints') or []))
    reason='Current data-pool disk' if str(Path(disk['path']).resolve()) in recorded else 'Disk is mounted or belongs to an active array' if held or busy else 'No stable disk identity' if not stable else 'Filesystem needs an import/unlock workflow' if fs not in FORMATS else ''
    result.append(dict(id=key,device=stable,path=node['path'],serial=disk.get('serial') or '',model=disk.get('model') or '',filesystem=fs,uuid=node.get('uuid'),label=node.get('label') or '',size=node['size'],eligible=not reason,reason=reason,mounted=own))
  return result
 def is_mounted(self,entry):
  result=self.run('findmnt','-J','--mountpoint',str(entry['mount']),'-o','SOURCE,FSTYPE,OPTIONS',check=False)
  if result.returncode:return False
  fs=json.loads(result.stdout)['filesystems'][0]
  source=fs['source'].split('[')[0]
  return 'ro' in fs['options'].split(',') and (str(Path(source).resolve())==str(Path(entry['device']).resolve()) or entry['filesystem']=='apfs' and fs['fstype'].startswith('fuse'))
 def action(self,data):
  with self.app.lock:
   if any(j.get('kind')=='storage' and j.get('state') in ('queued','running') for j in self.app.jobs.values()):raise self.error('Wait for the storage operation to finish.',409)
   ident=data.get('id');entry=self.mounted.get(ident)
   if data.get('action')=='unmount':
    if not entry or not self.is_mounted(entry):raise self.error('This drive is not mounted by Harbour.',409)
    self.run('umount',str(entry['mount']),timeout=30);self.mounted.pop(ident,None);self.save()
    return dict(unmounted=True)
   if data.get('action')!='mount':raise self.error('Choose mount or unmount.')
   disk=next((d for d in self.inventory() if d['id']==ident),None)
   if not disk or not disk['eligible']:raise self.error('Choose an unused supported disk. '+(disk or {}).get('reason',''),409)
   if disk['mounted']:return dict(mounted=True,id=ident)
   self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
   if any(p.is_symlink() for p in (self.root,*self.root.parents)):raise self.error('External mount location is redirected.',409)
   target=self.root/ident;target.mkdir(exist_ok=True,mode=0o700)
   if target.is_symlink() or target.is_mount():raise self.error('Mount location is in use.',409)
   # Re-read identities/topology immediately before mounting; never accept a raw browser path.
   latest=next((d for d in self.inventory() if d['id']==ident),None)
   if latest!=disk:raise self.error('Drive state changed. Refresh and try again.',409)
   fs=disk['filesystem']
   if fs=='btrfs':
    show=self.run('btrfs','filesystem','show','--raw',disk['device'],check=False).stdout
    if not re.search(r'Total devices\s+1\b',show):raise self.error('Multi-device Btrfs needs a separate pool import.',409)
   if fs=='apfs':
    volume=data.get('apfs_volume',1)
    if not isinstance(volume,int) or not 1<=volume<=128:raise self.error('Choose APFS volume 1–128.')
    self.run('fsapfsmount','-f',str(volume),'-X','ro,nosuid,nodev,noexec',disk['device'],str(target),timeout=30)
   else:self.run('mount','-t','ntfs-3g' if fs=='ntfs' else fs,'-o',FORMATS[fs],disk['device'],str(target),timeout=30)
   entry=dict(disk,mount=target);self.mounted[ident]=entry
   if not self.is_mounted(entry):
    self.run('umount',str(target),check=False);self.mounted.pop(ident,None)
    raise self.error('Could not verify a read-only mount.',409)
   self.save()
   return dict(mounted=True,id=ident)
 def path(self,ident,relative):
  entry=self.mounted.get(ident)
  if not entry or not self.is_mounted(entry):raise self.error('Mount this external disk first.',409)
  if not isinstance(relative,str) or len(relative)>2000:raise self.error('Invalid external path.')
  root=entry['mount'];path=root/relative
  if not path.resolve().is_relative_to(root.resolve()):raise self.error('Path is outside the external disk.',403)
  current=path
  while current!=root:
   if current.is_symlink():raise self.error('External symbolic links cannot be followed.',403)
   current=current.parent
  if not path.exists():raise self.error('File is unavailable.',404)
  return path
 def files(self,ident,relative):
  path=self.path(ident,relative)
  if not path.is_dir():raise self.error('Choose a folder.')
  entries=[]
  for p in sorted(path.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower())):
   if p.is_symlink():continue
   stat=p.stat()
   if not p.is_dir() and not p.is_file():continue
   entries.append(dict(name=p.name,directory=p.is_dir(),size=stat.st_size))
   if len(entries)>=2000:break
  return dict(path=relative,entries=entries,readonly=True)
 def install_support(self):
  if self.app.demo:raise self.error('Install filesystem support on the appliance.',409)
  def execute():
   self.app.job_progress('Installing filesystem readers','Installing signed Debian filesystem packages.')
   self.run('apt-get','update',timeout=300)
   self.run('env','DEBIAN_FRONTEND=noninteractive','NEEDRESTART_MODE=l','apt-get','install','-y','--no-install-recommends',*PACKAGES,timeout=900)
   return self.support()
  return self.app.job('Install filesystem readers',execute,kind='system')
