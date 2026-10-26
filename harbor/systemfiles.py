"""Owner-only file namespace on the OS SSD; never exposes the OS filesystem."""
import os,shutil
from pathlib import Path
from fileops import FileOperations

class SystemFileOperations(FileOperations):
 def action(self,data,actor):
  if data.get('operation')=='copy':
   source=self.item(data.get('path',''),allow_share=True);size=0;count=0
   paths=source.rglob('*') if source.is_dir() else [source]
   for path in paths:
    count+=1
    if count>10000:raise self.error('Copy smaller groups of files on the system SSD.',413)
    if path.is_file() and not path.is_symlink():size+=path.stat().st_size
   self.app.check_upload_space(size)
  return super().action(data,actor)

class SystemFiles:
 def __init__(self,app,root,contained,error,atomic):
  self.parent=app;self.storage=Path(root);self.error=error;self.contained=contained
  self.config={'shares':[{'name':'Files'}]}
  self.file_operations=SystemFileOperations(self,contained,error,atomic)
 def __getattr__(self,key):return getattr(self.parent,key)
 def prepare(self):
  if os.getenv('HARBOR_LIVE')=='1':raise self.error('System SSD files require an installed system.',409)
  # Reject redirects of the dedicated root or any existing ancestor.
  for path in (self.storage,*self.storage.parents):
   if path.is_symlink():raise self.error('The system data location is redirected. Manual review is required.',409)
  if (self.storage/'shares').is_symlink():raise self.error('The system data location is redirected.',409)
  folder=self.storage/'shares'/'Files'
  if folder.is_symlink():raise self.error('The system data folder is redirected.',409)
  folder.mkdir(parents=True,exist_ok=True)
  if not self.parent.demo and self.storage.stat().st_dev!=Path('/').stat().st_dev:raise self.error('The system data folder is not on the OS filesystem.',409)
  self.parent.owner(folder)
 def info(self):
  self.prepare();usage=shutil.disk_usage(self.storage)
  reserve=min(16*1024**3,max(2*1024**3,usage.total//20))
  return dict(name='System SSD',total=usage.total,free=usage.free,available=max(0,usage.free-reserve),reserve=reserve,path='Files',redundant=False)
 def check_upload_space(self,length):
  if length>self.info()['available']:raise self.error('The system SSD needs reserved free space for the OS. Choose the data pool or free some SSD space.',409)
 def require_storage(self):self.check_upload_space(1)
 def access_path(self,relative,username,write=False,allow_root=False):
  if not self.parent.admin or username!=self.parent.admin['username']:raise self.error('System SSD files are available only to the owner.',403)
  self.prepare()
  return type(self.parent).access_path(self,relative,username,write,allow_root)
 def files(self,relative):
  self.prepare()
  return type(self.parent).files(self,relative)
