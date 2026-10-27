import io,json,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
from externaldrives import ExternalDrives
from externalwrite import WRITABLE
class Error(Exception):
 def __init__(self,message,status=400):super().__init__(message)
class ExternalWriteTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
  self.app=SimpleNamespace(demo=True,state=self.root,config={},jobs={},lock=threading.RLock())
  self.run=Mock(return_value=SimpleNamespace(returncode=0,stdout=''))
  self.manager=ExternalDrives(self.app,self.run,Error)
  self.disk=dict(id='a'*24,device='/dev/disk/by-id/test-external',filesystem='ext4',serial='SERIAL',uuid='UUID',eligible=True,mounted=False)
  self.manager.inventory=Mock(return_value=[self.disk])
 def test_write_formats_exclude_mac_and_optical_readers(self):
  self.assertTrue({'ntfs','exfat','vfat','ext2','ext3','ext4','btrfs','xfs','f2fs'}<=WRITABLE)
  self.assertFalse(WRITABLE&{'apfs','hfs','hfsplus','udf','iso9660'})
 def test_write_mount_requires_disk_specific_confirmation_and_ack(self):
  for confirmation,ack in [('wrong',True),('WRITE SERIAL',False)]:
   with self.assertRaisesRegex(Error,'Confirm writing'):
    self.manager.action(dict(action='mount',id=self.disk['id'],mode='rw',confirmation=confirmation,acknowledge=ack))
  self.run.assert_not_called()
 def test_unsupported_write_mode_never_touches_disk(self):
  for fs in ('apfs','hfs','hfsplus','iso9660','udf'):
   self.disk['filesystem']=fs
   with self.assertRaisesRegex(Error,'read-only'):self.manager.action(dict(action='mount',id=self.disk['id'],mode='rw',confirmation='WRITE SERIAL',acknowledge=True))
  self.run.assert_not_called()
 def test_writes_cannot_bypass_readonly_mount(self):
  self.manager.mounted[self.disk['id']]=dict(self.disk,mount=self.root,writable=False)
  with self.assertRaisesRegex(Error,'Enable writing'):self.manager.upload(self.disk['id'],'','file.txt',io.BytesIO(b'x'),1)
  with self.assertRaisesRegex(Error,'Enable writing'):self.manager.file_action(dict(id=self.disk['id'],operation='mkdir',path='',name='Folder'))
  self.run.assert_not_called()
 def test_disk_newly_protected_as_pool_member_cannot_be_written(self):
  self.manager.mounted[self.disk['id']]=dict(self.disk,mount=self.root,writable=True)
  self.manager.is_mounted=Mock(return_value=True);self.disk['eligible']=False
  with self.assertRaisesRegex(Error,'protected'):self.manager.upload(self.disk['id'],'','file.txt',io.BytesIO(b'x'),1)
  self.assertFalse((self.root/'file.txt').exists())
 def test_path_traversal_rejected_before_any_file_operation(self):
  for path in ('../outside','/etc','folder/../outside'):
   with self.assertRaises(Error):self.manager.file_action(dict(id=self.disk['id'],operation='delete',path=path,confirmation='DELETE outside'))
  for name in ('../outside','folder/file','..','x\\y'):
   with self.assertRaises(Error):self.manager.upload(self.disk['id'],'',name,io.BytesIO(b'x'),1)
  self.run.assert_not_called()
 def test_fat32_large_upload_refused_before_opening_a_file(self):
  entry=dict(self.disk,mount=self.root,writable=True,filesystem='vfat')
  self.manager.writable=Mock(return_value=entry)
  with self.assertRaisesRegex(Error,'4 GiB'):self.manager.upload(self.disk['id'],'','large.bin',io.BytesIO(),4*1024**3)
 def test_findmnt_must_match_rw_mode_and_mount_protections(self):
  entry=dict(self.disk,mount=self.root,writable=True)
  for options,allowed in [('rw,nosuid,nodev,noexec',True),('ro,nosuid,nodev,noexec',False),('rw,nodev',False)]:
   self.run.return_value.stdout=json.dumps({'filesystems':[dict(source=entry['device'],fstype='ext4',options=options)]})
   self.assertEqual(self.manager.is_mounted(entry),allowed)
 def test_failed_write_mount_falls_back_to_readonly_without_forcing(self):
  self.manager.inventory=lambda:[dict(self.disk,mounted=self.disk['id'] in self.manager.mounted)]
  self.manager.is_mounted=lambda entry: not entry.get('writable')
  def run(*args,**kwargs):
   if args[0]=='mount' and 'rw,' in args[4]:raise Error('driver refused write mode')
   return SimpleNamespace(returncode=0,stdout='')
  self.run.side_effect=run
  with self.assertRaisesRegex(Error,'driver refused'):
   self.manager.action(dict(action='mount',id=self.disk['id'],mode='rw',confirmation='WRITE SERIAL',acknowledge=True))
  self.assertFalse(self.manager.mounted[self.disk['id']]['writable'])
  self.assertFalse(any('force' in str(c.args) or 'remove_hiberfile' in str(c.args) for c in self.run.call_args_list))
 def test_restart_only_restores_mount_records_and_never_mounts_disks(self):
  self.manager.mounted[self.disk['id']]=dict(self.disk,mount=self.root/self.disk['id'],writable=True)
  self.manager.save()
  restored=ExternalDrives(self.app,self.run,Error)
  self.assertTrue(restored.mounted[self.disk['id']]['writable'])
  self.run.assert_not_called()
if __name__=='__main__':unittest.main()
