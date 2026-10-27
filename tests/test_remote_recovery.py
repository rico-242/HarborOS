import gzip,json,stat,sys,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
from remote_recovery import cpio_archive
import remote_agent
class RemoteRecoveryTests(unittest.TestCase):
 def test_overlay_contains_only_exact_files_and_modes(self):
  raw=gzip.decompress(cpio_archive([('harbour-remote',b'',stat.S_IFDIR|0o700),('harbour-remote/key',b'private-test-bytes',stat.S_IFREG|0o600)]));offset=0;records={}
  while True:
   self.assertEqual(raw[offset:offset+6],b'070701');fields=[int(raw[offset+6+i*8:offset+14+i*8],16) for i in range(13)];offset+=110
   name=raw[offset:offset+fields[11]-1].decode();offset+=fields[11];offset=(offset+3)//4*4
   data=raw[offset:offset+fields[6]];offset+=fields[6];offset=(offset+3)//4*4
   if name=='TRAILER!!!':break
   records[name]=(data,fields[1])
  self.assertEqual(set(records),{'harbour-remote','harbour-remote/key'});self.assertEqual(records['harbour-remote/key'],(b'private-test-bytes',stat.S_IFREG|0o600))
 def test_installer_cannot_run_again_after_fresh_install(self):
  with self.assertRaisesRegex(ValueError,'RAM recovery'):remote_agent.install({'phase':'setup'},{'confirmation':'ERASE example'})
 def test_wrong_serial_confirmation_cannot_touch_disks(self):
  command=Mock();command.read_text.return_value='harbour.recovery=1'
  with patch.object(remote_agent,'Path',return_value=command),patch.object(remote_agent,'load_installer') as loader:
   with self.assertRaisesRegex(ValueError,'serial'):remote_agent.install({'phase':'installer','disk':{'serial':'OS-SSD'}},{'confirmation':'ERASE other'})
   loader.assert_not_called()

 def test_unplanned_pool_cannot_be_erased(self):
  with self.assertRaisesRegex(ValueError,'authorized'):remote_agent.create_pool({'phase':'setup'},{'confirmation':'ERASE POOL Main-Storage'})
 def test_pool_requires_separate_exact_confirmation(self):
  with self.assertRaisesRegex(ValueError,'Confirm'):remote_agent.create_pool({'phase':'setup','pool':{'mode':'hybrid1','name':'Main-Storage'}},{'confirmation':'yes'})
 def test_pool_reset_refused_after_owner_setup(self):
  with patch.object(remote_agent,'Path') as path:
   path.return_value.exists.return_value=True
   with self.assertRaisesRegex(ValueError,'first-owner'):remote_agent.create_pool({'phase':'setup','pool':{'mode':'hybrid1','name':'Main-Storage'}},{'confirmation':'ERASE POOL Main-Storage'})

 def test_efi_registration_tools_required_before_erasure(self):
  with patch.object(remote_agent,'Path') as path,patch.object(remote_agent.shutil,'which',return_value=None),patch.object(remote_agent,'run') as run:
   path.return_value.is_dir.return_value=True
   with self.assertRaisesRegex(ValueError,'No disk was erased'):remote_agent.check_efi_writes({'disk':{},'efi_part':2})
   run.assert_not_called()
 def test_changed_disk_cannot_reach_installer(self):
  command=Mock();command.read_text.return_value='harbour.recovery=1';command.exists.return_value=False
  module=Mock();module.inventory.return_value=[{'id':'planned','size':200,'serial':'OS','wwn':''}]
  with patch.object(remote_agent,'Path',return_value=command),patch.object(remote_agent,'load_installer',return_value=module):
   with self.assertRaisesRegex(ValueError,'changed'):remote_agent.install({'phase':'installer','disk':{'id':'planned','size':100,'serial':'OS','wwn':''}},{'confirmation':'ERASE OS'})
   module.install.assert_not_called()
 def test_network_bootstrap_is_bound_to_mac_and_address(self):
  from remote_recovery import network_configuration
  text=network_configuration({'mac':'52:54:00:12:34:56','address':'192.168.1.97/24','gateway':'192.168.1.1','dns':['192.168.1.1']})
  self.assertIn('MACAddress=52:54:00:12:34:56',text);self.assertIn('Address=192.168.1.97/24',text);self.assertIn('DHCP=no',text)
