"""Confined file operations and a recoverable recycle bin."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import shutil
import os
import errno
import ctypes
import sys


def filename(value):
    if not isinstance(value,str) or not 1<=len(value)<=200 or value in ('.','..') or re.search(r'[\x00-\x1f<>:"/\\|?*]',value) or value.endswith((' ','.')):
        raise ValueError('Use a file name without slashes or special system characters.')
    return value


def exclusive_copy(source,target):
    with source.open('rb') as original,target.open('xb') as copy:
        cloned=False
        if sys.platform.startswith('linux'):
            import fcntl
            try:fcntl.ioctl(copy.fileno(),0x40049409,original.fileno());cloned=True
            except OSError:pass
        if not cloned:shutil.copyfileobj(original,copy,1024*1024)
        copy.flush();os.fsync(copy.fileno())
    shutil.copystat(source,target,follow_symlinks=False)
    return target


def transfer(source,target,copy=False):
    if not copy:
        if sys.platform.startswith('linux'):
            libc=ctypes.CDLL(None,use_errno=True)
            rename=getattr(libc,'renameat2',None)
            if rename:
                result=rename(-100,os.fsencode(source),-100,os.fsencode(target),1)
                if result==0:return
                error=ctypes.get_errno()
                if error not in (errno.EXDEV,errno.ENOSYS):raise OSError(error,os.strerror(error),str(target))
        elif sys.platform=='win32':
            source.rename(target);return
    if source.is_dir():
        shutil.copytree(source,target,symlinks=True,copy_function=lambda a,b:exclusive_copy(Path(a),Path(b)))
        if not copy:shutil.rmtree(source)
    else:
        exclusive_copy(source,target)
        if not copy:source.unlink()


class FileOperations:
    def __init__(self,app,contained,error,atomic):
        self.app,self.contained,self.error,self.atomic=app,contained,error,atomic

    def item(self,relative,allow_share=False):
        root=self.app.storage/'shares'
        path=self.contained(root,relative)
        parts=path.relative_to(root.resolve()).parts
        if len(parts)<(1 if allow_share else 2) or not path.exists():
            raise self.error('Choose a file or folder inside a shared folder.',409)
        return path

    def target(self,data,source):
        try:name=filename(data.get('name',source.name))
        except ValueError as error:raise self.error(str(error))
        parent=self.contained(self.app.storage/'shares',data.get('destination',''))
        if not parent.is_dir() or parent==(self.app.storage/'shares').resolve():
            raise self.error('Choose a destination inside a shared folder.')
        target=self.contained(parent,name)
        if target.exists() or target.is_symlink():
            raise self.error('A file with that name already exists.',409)
        if source.is_dir() and target.is_relative_to(source):
            raise self.error('A folder cannot be moved or copied inside itself.')
        return target

    def action(self,data,actor):
        self.app.require_storage()
        operation=data.get('operation')
        source=self.item(data.get('path',''),allow_share=operation=='copy')
        if hasattr(self.app,'members'):
            self.app.access_path(data.get('path',''),actor,write=operation!='copy')
            if operation in ('copy','move'):self.app.access_path(data.get('destination',''),actor,write=True)
        if operation=='trash':
            root=self.app.storage/'.trash';root.mkdir(mode=0o700,exist_ok=True)
            ident=secrets.token_hex(16)
            metadata={'id':ident,'name':source.name,'path':source.relative_to((self.app.storage/'shares').resolve()).as_posix(),
                      'directory':source.is_dir(),'deleted':datetime.now(timezone.utc).isoformat(),'actor':actor}
            self.atomic(root/(ident+'.json'),metadata)
            try:transfer(source,root/ident)
            except Exception:
                (root/(ident+'.json')).unlink(missing_ok=True)
                raise
            self.app.event('Moved “'+source.name+'” to the recycle bin.')
            return metadata
        if operation not in ('rename','move','copy'):
            raise self.error('Unknown file operation.')
        if operation=='rename':
            data=dict(data,destination=source.parent.relative_to((self.app.storage/'shares').resolve()).as_posix())
        target=self.target(data,source)
        if operation=='copy':
            transfer(source,target,copy=True)
            self.app.owner(target)
        else:
            transfer(source,target)
        label={'copy':'Copied','move':'Moved','rename':'Renamed'}[operation]
        self.app.event(f'{label} “{source.name}”.')
        return {'name':target.name}

    def trash(self):
        result=[]
        for path in (self.app.storage/'.trash').glob('*.json'):
            try:
                value=json.loads(path.read_text())
                if re.fullmatch(r'[a-f0-9]{32}',value.get('id','')) and path.with_suffix('').exists():result.append(value)
            except (OSError,ValueError):continue
        return sorted(result,key=lambda x:x['deleted'],reverse=True)

    def restore(self,ident):
        self.app.require_storage()
        if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident):raise self.error('Invalid recycle-bin item.')
        root=self.app.storage/'.trash';meta=root/(ident+'.json')
        if not meta.exists() or not (root/ident).exists():raise self.error('This recycle-bin item is unavailable.',404)
        value=json.loads(meta.read_text())
        target=self.contained(self.app.storage/'shares',value['path'])
        if target.exists() or target.is_symlink():raise self.error('The original name is already in use. Rename that item before restoring.',409)
        if not target.parent.is_dir():raise self.error('The original folder is missing. Recreate it before restoring.',409)
        transfer(root/ident,target);meta.unlink()
        self.app.event('Restored “'+value['name']+'” from the recycle bin.')
        return {'name':target.name}
