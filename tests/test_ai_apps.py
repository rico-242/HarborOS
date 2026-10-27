import copy,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
import appstore,server
class AppRuntimeTests(unittest.TestCase):
 def setUp(self):self.item=appstore.OFFICIAL['openclaw']
 def container(self,service,state='running',status='Up 1 minute',oneoff=False):return dict(State=state,Status=status,Labels='com.docker.compose.project=harbor-openclaw,com.docker.compose.service='+service+',com.docker.compose.oneoff='+str(oneoff))
 def test_successful_setup_container_does_not_hide_running_gateway(self):
  self.assertEqual(appstore.compose_app_state(self.item,[self.container('openclaw'),self.container('openclaw-init','exited','Exited (0) 1 minute ago')]),'running')
 def test_failed_setup_is_not_treated_as_success(self):
  self.assertEqual(appstore.compose_app_state(self.item,[self.container('openclaw'),self.container('openclaw-init','exited','Exited (1) 1 minute ago')]),'stopped')
 def test_normal_daemon_exit_zero_is_still_stopped(self):
  self.assertEqual(appstore.compose_app_state(self.item,[self.container('openclaw','exited','Exited (0) 1 minute ago')]),'stopped')
 def test_restart_loop_is_reported_explicitly(self):
  self.assertEqual(appstore.compose_app_state(self.item,[self.container('openclaw','restarting','Restarting (1)')]),'restarting')
 def test_ad_hoc_oneoff_container_does_not_hide_running_gateway(self):
  self.assertEqual(appstore.compose_app_state(self.item,[self.container('openclaw'),self.container('openclaw','exited','Exited (1)',True)]),'running')
 def test_setup_container_alone_is_not_a_running_application(self):
  self.assertEqual(appstore.compose_app_state(self.item,[self.container('openclaw-init')]),'stopped')
 def test_real_app_list_uses_dependency_aware_state(self):
  with tempfile.TemporaryDirectory() as folder:
   app=SimpleNamespace(demo=False,state=Path(folder))
   values=[dict(self.container('openclaw'),Names='harbor-openclaw-openclaw-1'),dict(self.container('openclaw-init','exited','Exited (0) 1 minute ago'),Names='harbor-openclaw-openclaw-init-1')]
   with patch('server.run',return_value=SimpleNamespace(returncode=0,stdout='\n'.join(json.dumps(v) for v in values))):
    item=next(a for a in server.Harbor.app_list(app) if a['id']=='openclaw')
   self.assertEqual(item['state'],'running');self.assertTrue(item['installed'])
class AppStorageTests(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name);self.apps=self.root/'apps';self.storage=self.root/'storage';self.folder=self.apps/'anythingllm/storage'
 def compose(self,folder=None):return {'services':{'anythingllm':{'volumes':[{'type':'bind','source':str(folder or self.folder),'target':'/app/server/storage'}]}}}
 def test_storage_owned_by_container_without_changing_existing_files(self):
  self.folder.mkdir(parents=True);data=self.folder/'anythingllm.db';data.write_bytes(b'preserved database')
  with patch.object(appstore.os,'chown',create=True) as chown,patch.object(appstore.os,'chmod') as chmod:
   appstore.provision_app_mounts('anythingllm',self.compose(),self.apps,self.storage)
  chown.assert_called_once_with(self.folder,1000,1000);self.assertEqual(data.read_bytes(),b'preserved database')
  self.assertEqual(chmod.call_args.args[1]&0o700,0o700)
 def test_new_storage_prepared_for_first_install(self):
  with patch.object(appstore.os,'chown',create=True) as chown:
   appstore.provision_app_mounts('anythingllm',self.compose(),self.apps,self.storage)
  self.assertTrue(self.folder.is_dir());chown.assert_called_once_with(self.folder,1000,1000)
 def test_other_apps_do_not_get_arbitrary_ownership_changes(self):
  with patch.object(appstore.os,'chown',create=True) as chown:
   appstore.provision_app_mounts('other',self.compose(),self.apps,self.storage)
  chown.assert_not_called()
 def test_shared_folder_cannot_be_taken_over_for_anythingllm(self):
  shared=self.storage/'shares/Private'
  with patch.object(appstore.os,'chown',create=True) as chown:
   with self.assertRaisesRegex(ValueError,'dedicated'):appstore.provision_app_mounts('anythingllm',self.compose(shared),self.apps,self.storage)
  chown.assert_not_called();self.assertFalse(shared.exists())
