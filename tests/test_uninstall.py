import json,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
import server

class UninstallTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  root=Path(self.temp.name);self.folder=root/'state/compose/jellyfin';self.folder.mkdir(parents=True)
  self.config=self.folder/'compose.json';self.config.write_text('{"services":{}}')
  self.data=root/'apps/jellyfin/config';self.data.mkdir(parents=True);(self.data/'keep.txt').write_text('preserve')
  self.app=SimpleNamespace(demo=False,state=root/'state',apps=root/'apps',storage=root/'storage',lock=threading.RLock(),config={'apps':['jellyfin','tailscale']},save=Mock(),job_progress=Mock())
  self.app.job=lambda title,execute,**kw:execute()
  self.run=Mock(side_effect=lambda *a,**kw:SimpleNamespace(returncode=1 if a[:3]==('docker','container','inspect') else 0,stdout=''))
 def uninstall(self,options=None):
  with patch('server.run',self.run),patch('server.shutil.which',return_value=None):
   return server.Harbor.app_action(self.app,'jellyfin','uninstall',options)
 def test_requires_exact_confirmation_before_any_docker_operation(self):
  for options in (None,{}, {'confirmation':'UNINSTALL tailscale'}):
   with self.assertRaises(server.APIError):self.uninstall(options)
  self.run.assert_not_called();self.assertTrue(self.config.exists())
 def test_compose_uninstall_preserves_data_images_volumes_and_saved_config(self):
  result=self.uninstall({'confirmation':'UNINSTALL jellyfin'})
  commands=[call.args for call in self.run.call_args_list]
  down=next(command for command in commands if command[-1]=='down')
  self.assertNotIn('--volumes',down);self.assertNotIn('-v',down);self.assertNotIn('--rmi',down)
  self.assertFalse(self.config.exists());self.assertTrue((self.folder/'compose.uninstalled.json').exists())
  self.assertEqual((self.data/'keep.txt').read_text(),'preserve')
  self.assertEqual(self.app.config['apps'],['tailscale']);self.assertTrue(result['data_preserved'])
 def test_failed_removal_keeps_install_record(self):
  def execute(*args,**kw):
   if args[-1]=='down':raise RuntimeError('Docker unavailable')
   return SimpleNamespace(returncode=1,stdout='')
  self.run.side_effect=execute
  with self.assertRaisesRegex(RuntimeError,'Docker unavailable'):self.uninstall({'confirmation':'UNINSTALL jellyfin'})
  self.assertTrue(self.config.exists());self.assertIn('jellyfin',self.app.config['apps']);self.app.save.assert_not_called()
 def test_legacy_container_removal_never_deletes_volumes_or_images(self):
  self.run.side_effect=None;self.run.return_value=SimpleNamespace(returncode=0,stdout='')
  self.uninstall({'confirmation':'UNINSTALL jellyfin'})
  self.assertIn(unittest.mock.call('docker','rm','--force','harbor-jellyfin',timeout=90),self.run.call_args_list)
  self.assertTrue((self.data/'keep.txt').exists());self.assertFalse(self.config.exists());self.assertNotIn('jellyfin',self.app.config['apps'])

if __name__=='__main__':unittest.main()
