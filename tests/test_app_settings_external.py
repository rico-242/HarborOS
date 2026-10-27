import hashlib,json,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
from appsettings import AppSettings
from externaldrives import ExternalDrives,FORMATS
class Error(Exception):
 def __init__(self,message,status=400):super().__init__(message)
class AppSettingsTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);root=Path(t.name);self.root=root
  self.app=SimpleNamespace(demo=True,state=root/'state',apps=root/'apps',lock=threading.RLock(),jobs={},job_context=threading.local(),job_progress=Mock())
  self.app.job=lambda title,fn,**kw:fn()
  self.config=root/'state/compose/jellyfin/compose.json';self.config.parent.mkdir(parents=True)
  self.config.write_text(json.dumps({'services':{'jellyfin':{'image':'jellyfin/jellyfin','environment':{'TZ':'UTC'}}}}))
  self.data=root/'apps/jellyfin';self.data.mkdir(parents=True);(self.data/'settings.json').write_text('{"value":1}')
  self.run=Mock(return_value=SimpleNamespace(returncode=0,stdout=''))
  self.manager=AppSettings(self.app,self.run,Error,Mock())
 def payload(self):
  info=self.manager.info('jellyfin');return dict(id='jellyfin',revision=info['revision'],compose=info['compose'],confirmation='APPLY jellyfin')
 def test_location_and_editable_files_are_explicit(self):
  info=self.manager.info('jellyfin');self.assertEqual(info['location']['location'],'OS drive');self.assertIn('settings.json',info['files'])
 def test_settings_are_validated_then_app_recreated(self):
  data=self.payload();data['compose']['services']['jellyfin']['environment']['TZ']='Europe/London'
  self.assertTrue(self.manager.save(data)['saved']);self.assertIn('Europe/London',self.config.read_text())
  self.assertEqual(self.run.call_args_list[0].args[-2:],('config','--quiet'))
  self.assertEqual(self.run.call_args_list[1].args[-3:],('up','-d','--force-recreate'))
 def test_failed_apply_restores_exact_original_configuration(self):
  original=self.config.read_bytes();self.run.side_effect=[None,RuntimeError('cannot start'),None]
  data=self.payload();data['compose']['services']['jellyfin']['image']='bad/image'
  with self.assertRaisesRegex(Error,'restored'):self.manager.save(data)
  self.assertEqual(self.config.read_bytes(),original)
 def test_stale_revision_and_missing_confirmation_cannot_write(self):
  for update in ({'revision':'old'},{'confirmation':'wrong'}):
   data=self.payload();data.update(update)
   with self.assertRaises(Error):self.manager.save(data)
  self.run.assert_not_called()
 def test_text_file_edit_preserves_other_files(self):
  info=self.manager.info('jellyfin','settings.json')
  self.manager.save(dict(id='jellyfin',path='settings.json',content='{"value":2}',revision=info['revision'],confirmation='APPLY jellyfin'))
  self.assertEqual((self.data/'settings.json').read_text(),'{"value":2}')
  self.assertIn('jellyfin/jellyfin',self.config.read_text())
 def test_outside_paths_and_binary_files_are_rejected(self):
  (self.data/'binary.json').write_bytes(b'\x00secret')
  for name in ('../../state/compose/jellyfin/compose.json','binary.json'):
   with self.assertRaises(Error):self.manager.file('jellyfin',name)
 def test_new_app_plan_works_without_a_data_pool(self):
  import server
  app=server.Harbor(self.root/'other-state',self.root/'pool',self.root/'ssd-apps',demo=True)
  try:
   app.storage_info=lambda:{'mounted':False}
   with patch('server.prepare_app',return_value={'compose':{}}) as prepare:
    plan=app.app_plan('jellyfin')
    self.assertEqual(prepare.call_args.args[2],app.system_files.storage)
   self.assertEqual(plan['media_root'],str(app.system_files.storage))
   self.assertEqual(plan['app_location'],str(app.apps/'jellyfin'))
   self.assertNotIn(str(app.storage),json.dumps(plan['compose']))
  finally:app.pool.shutdown(wait=True)
 def test_source_build_and_external_include_rejected(self):
  data=self.payload();data['compose']['services']['jellyfin']['build']='.'
  with self.assertRaises(Error):self.manager.save(data)
  self.run.assert_not_called()
class ExternalTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
  self.app=SimpleNamespace(demo=True,state=self.root,config={},jobs={},lock=threading.RLock())
  self.run=Mock(return_value=SimpleNamespace(returncode=0,stdout=''))
  self.manager=ExternalDrives(self.app,self.run,Error)
 def test_nested_partition_filesystems_detected_and_system_disk_excluded(self):
  self.app.demo=False
  tree=[dict(path='/dev/vda',type='disk',children=[dict(path='/dev/vda1',fstype='ext4',mountpoints=['/'])]),dict(path='/dev/vdb',type='disk',serial='USB-1',children=[dict(path='/dev/vdb1',fstype='exfat',uuid='uuid',size=1234,label='Portable',mountpoints=[])])]
  self.run.return_value.stdout=json.dumps({'blockdevices':tree})
  values=self.manager.inventory()
  self.assertEqual(len(values),1)
  self.assertEqual(values[0]['filesystem'],'exfat')
  self.assertEqual(values[0]['serial'],'USB-1')
  self.assertIn('--tree',self.run.call_args.args)
 def test_all_normal_mounts_are_readonly_and_nonexecutable(self):
  for fs,options in FORMATS.items():
   self.assertTrue({'ro','nosuid','nodev','noexec'}.issubset(options.split(',')),fs)
  for fs in ('ext3','ext4'):self.assertIn('noload',FORMATS[fs])
  self.assertIn('norecovery',FORMATS['xfs']);self.assertIn('nologreplay',FORMATS['btrfs'])
 def test_no_raw_browser_device_can_be_mounted(self):
  self.manager.inventory=Mock(return_value=[])
  with self.assertRaises(Error):self.manager.action(dict(action='mount',id='/dev/sda'))
  self.run.assert_not_called()
 def test_protected_volume_is_never_mounted(self):
  self.manager.inventory=Mock(return_value=[dict(id='test',eligible=False,reason='Pool disk')])
  with self.assertRaisesRegex(Error,'Pool disk'):self.manager.action(dict(action='mount',id='test'))
  self.run.assert_not_called()
 def test_read_requires_a_verified_readonly_mount(self):
  folder=self.root/'volume';folder.mkdir();(folder/'file.txt').write_text('hello')
  self.manager.mounted['test']=dict(mount=folder,device='/dev/fake',filesystem='ext4')
  self.manager.is_mounted=Mock(return_value=False)
  with self.assertRaises(Error):self.manager.files('test','')
  self.manager.is_mounted.return_value=True
  self.assertEqual(self.manager.files('test','')['entries'][0]['name'],'file.txt')
  with self.assertRaises(Error):self.manager.path('test','../outside')
 def test_ro_mount_verification_rejects_rw(self):
  self.run.return_value.stdout=json.dumps({'filesystems':[dict(source='/dev/fake',fstype='ext4',options='rw,nosuid,nodev')]})
  self.assertFalse(self.manager.is_mounted(dict(mount=self.root,device='/dev/fake',filesystem='ext4')))
 def test_storage_work_blocks_external_mount_changes(self):
  self.app.jobs={'job':dict(kind='storage',state='running')}
  with self.assertRaisesRegex(Error,'Wait'):self.manager.action(dict(action='mount',id='test'))
  self.run.assert_not_called()
if __name__=='__main__':unittest.main()
