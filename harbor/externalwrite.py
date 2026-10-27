"""Owner-only writes confined to a verified, explicitly writable external mount."""
import ctypes,errno,os,secrets,shutil,stat
from contextlib import contextmanager
WRITABLE={'ext2','ext3','ext4','btrfs','xfs','vfat','exfat','ntfs','f2fs'}
def rename_exclusive(source_fd,source,target_fd,target):
 libc=ctypes.CDLL(None,use_errno=True)
 function=libc.renameat2
 function.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
 function.restype=ctypes.c_int
 if function(source_fd,os.fsencode(source),target_fd,os.fsencode(target),1)==0:return
 code=ctypes.get_errno()
 if code not in (errno.EINVAL,errno.ENOSYS,errno.EOPNOTSUPP):raise OSError(code,os.strerror(code))
 # Older FUSE NTFS drivers lack renameat2 flags. Hard-link publication is
 # still atomic and exclusive for regular files; directory replacement uses
 # an exclusively created empty reservation while the manager holds io_lock.
 info=os.stat(source,dir_fd=source_fd,follow_symlinks=False)
 if stat.S_ISREG(info.st_mode):
  os.link(source,target,src_dir_fd=source_fd,dst_dir_fd=target_fd,follow_symlinks=False)
  os.unlink(source,dir_fd=source_fd)
 elif stat.S_ISDIR(info.st_mode):
  os.mkdir(target,mode=0o700,dir_fd=target_fd)
  reserved=os.stat(target,dir_fd=target_fd,follow_symlinks=False)
  try:os.rename(source,target,src_dir_fd=source_fd,dst_dir_fd=target_fd)
  except Exception:
   current=os.stat(target,dir_fd=target_fd,follow_symlinks=False)
   if (current.st_dev,current.st_ino)==(reserved.st_dev,reserved.st_ino):os.rmdir(target,dir_fd=target_fd)
   raise
 else:raise OSError(errno.EINVAL,'Choose a regular file or folder')
class ExternalWrites:
 def write_confirmation(self,disk):return 'WRITE '+(disk.get('serial') or disk.get('uuid') or disk['id'])
 def new_owner(self,entry):
  if entry['filesystem'] not in {'ext2','ext3','ext4','btrfs','xfs','f2fs'}:return None
  admin=getattr(self.app,'admin',None)
  if admin:
   import pwd
   user=pwd.getpwnam(admin['username']);return user.pw_uid,user.pw_gid
  return os.geteuid(),os.getegid()
 def writable(self,ident):
  entry=self.mounted.get(ident)
  if not entry or not entry.get('writable') or entry['filesystem'] not in WRITABLE or not self.is_mounted(entry):
   raise self.error('Enable writing for this external disk before changing files.',409)
  disk=next((d for d in self.inventory() if d['id']==ident),None)
  if not disk or not disk['eligible']:raise self.error('The disk is now protected or unavailable. Refresh connected disks.',409)
  return entry
 def filename(self,name):
  if not isinstance(name,str) or not name or name in ('.','..') or '/' in name or '\\' in name or len(name.encode('utf-8'))>240 or any(ord(c)<32 for c in name) or name.startswith('.harbour-upload-'):
   raise self.error('Use a filename without slashes or control characters, up to 240 UTF-8 bytes.')
  return name
 @contextmanager
 def directory(self,ident,relative):
  entry=self.writable(ident)
  if not isinstance(relative,str) or relative.startswith('/') or '\\' in relative or any(p in ('.','..') for p in relative.split('/') if p):raise self.error('Invalid external folder.',403)
  flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
  fd=os.open(entry['mount'],flags)
  try:
   for component in filter(None,relative.split('/')):
    next_fd=os.open(component,flags,dir_fd=fd);os.close(fd);fd=next_fd
   yield fd
  except OSError as error:
   if error.errno in (errno.ELOOP,errno.ENOTDIR):raise self.error('Symbolic links cannot be followed.',403)
   raise
  finally:os.close(fd)
 def file_action(self,data):
  with self.io_lock:
   ident=data.get('id');operation=data.get('operation');relative=data.get('path','')
   if not isinstance(relative,str) or relative.startswith('/') or any(p in ('.','..') for p in relative.split('/') if p):raise self.error('Invalid external path.',403)
   if operation=='mkdir':
    name=self.filename(data.get('name'))
    with self.directory(ident,relative) as fd:
     try:
      os.mkdir(name,mode=0o750,dir_fd=fd)
      owner=self.new_owner(self.mounted[ident])
      if owner:os.chown(name,*owner,dir_fd=fd,follow_symlinks=False)
     except FileExistsError:raise self.error('A file or folder with that name already exists.',409)
   elif operation in ('rename','delete'):
    parts=relative.rstrip('/').split('/');name=self.filename(parts[-1]);parent='/'.join(parts[:-1])
    with self.directory(ident,parent) as fd:
     info=os.stat(name,dir_fd=fd,follow_symlinks=False)
     if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):raise self.error('Choose a regular file or folder. Links are protected.',403)
     if operation=='rename':
      target=self.filename(data.get('name'))
      try:rename_exclusive(fd,name,fd,target)
      except FileExistsError:raise self.error('A file or folder with that name already exists.',409)
     else:
      if data.get('confirmation')!='DELETE '+name:raise self.error('Type DELETE '+name+' to permanently delete this item.')
      if stat.S_ISDIR(info.st_mode):
       if not shutil.rmtree.avoids_symlink_attacks:raise self.error('Secure folder deletion is unavailable.',409)
       shutil.rmtree(name,dir_fd=fd)
      else:os.unlink(name,dir_fd=fd)
   else:raise self.error('Choose create folder, rename or delete.')
   return dict(ok=True,operation=operation)
 def upload(self,ident,relative,name,stream,length):
  name=self.filename(name)
  if not isinstance(length,int) or not 0<=length<=1024**4:raise self.error('Invalid upload size.',413)
  with self.io_lock:
   entry=self.writable(ident)
   if entry['filesystem']=='vfat' and length>=4*1024**3:raise self.error('FAT32 files must be smaller than 4 GiB. Use exFAT or another format.',413)
   with self.directory(ident,relative) as fd:
    usage=os.fstatvfs(fd)
    if length>max(0,usage.f_bavail*usage.f_frsize-16*1024**2):raise self.error('This external disk does not have enough free space.',409)
    try:os.stat(name,dir_fd=fd,follow_symlinks=False)
    except FileNotFoundError:pass
    else:raise self.error('A file with that name already exists.',409)
    temporary='.harbour-upload-'+secrets.token_hex(16)+'.part'
    out=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640,dir_fd=fd)
    try:
     with os.fdopen(out,'wb') as destination:
      owner=self.new_owner(entry)
      if owner:os.fchown(destination.fileno(),*owner)
      remaining=length
      while remaining:
       chunk=stream.read(min(256*1024,remaining))
       if not chunk:raise self.error('Upload interrupted. No completed file was created.',400)
       destination.write(chunk);remaining-=len(chunk)
      destination.flush();os.fsync(destination.fileno())
     try:rename_exclusive(fd,temporary,fd,name)
     except FileExistsError:raise self.error('A file with that name appeared during upload; it was not overwritten.',409)
     os.fsync(fd)
    finally:
     try:os.unlink(temporary,dir_fd=fd)
     except FileNotFoundError:pass
  return dict(uploaded=True,name=name,bytes=length)
