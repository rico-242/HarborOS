import importlib.util,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('tested_remote_client',root/'tools/remote-reinstall.py');client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
class ClientReconnectTests(unittest.TestCase):
 def test_status_poll_reconnects_when_reboot_closes_old_session(self):
  old,new=Mock(),Mock()
  with patch.object(client,'recovery_connection',side_effect=[old,new]),patch.object(client,'agent',side_effect=[EOFError('reboot'),{'phase':'setup'}]),patch.object(client.time,'sleep'):
   self.assertIs(client.wait_connection('nas',None,{'server_key':'test'},phase='setup'),new)
  old.close.assert_called_once();new.close.assert_not_called()
 def test_unexpected_ssh_identity_stops_retries(self):
  with patch.object(client,'recovery_connection',side_effect=client.paramiko.AuthenticationException),patch.object(client.time,'sleep') as sleep:
   with self.assertRaisesRegex(RuntimeError,'No install command'):client.wait_connection('nas',None,{'server_key':'test'})
   sleep.assert_not_called()
