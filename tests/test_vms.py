import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'harbor'))
from vms import VirtualMachines
class VMs(unittest.TestCase):
 def test_invalid_name(self):
  with self.assertRaises(ValueError): VirtualMachines(None,ValueError).action({'name':'bad name','action':'start'})
 def test_list(self):
  p=type('P',(),{'stdout':' Id   Name   State\n--------------------\n 1    testvm running\n'})()
  with patch('vms.subprocess.run',return_value=p): self.assertEqual(VirtualMachines(None,ValueError).info()['vms'][0]['name'],'testvm')
 def test_stopped_guest_listed(self):
  p=type('P',(),{'stdout':' Id   Name   State\n--------------------\n -    installed shut off\n'})()
  with patch('vms.subprocess.run',return_value=p):self.assertEqual(VirtualMachines(None,ValueError).info()['vms'][0]['state'],'shut off')
 def test_console_rejects_nonlocal_listener(self):
  vm=VirtualMachines(None,ValueError)
  p=type('P',(),{'stdout':'<domain><devices><graphics type="vnc" listen="0.0.0.0" port="5900"/></devices></domain>'})()
  with patch.object(vm,'_run',return_value=p),self.assertRaises(ValueError):vm.console_address('guest')
 def test_console_local_address(self):
  vm=VirtualMachines(None,ValueError)
  p=type('P',(),{'stdout':'<domain><devices><graphics type="vnc" listen="127.0.0.1" port="5901"/></devices></domain>'})()
  with patch.object(vm,'_run',return_value=p):self.assertEqual(vm.console_address('guest'),('127.0.0.1',5901))
 def test_force_off_confirmation(self):
  vm=VirtualMachines(None,ValueError)
  with patch.object(vm,'_run') as run,self.assertRaises(ValueError):
   vm.action({'name':'guest','action':'destroy'})
  run.assert_not_called()
 def test_eject_already_empty(self):
  vm=VirtualMachines(None,ValueError)
  p=type('P',(),{'stdout':'<domain><devices><disk device="cdrom"><target dev="hdb"/></disk></devices></domain>'})()
  with patch.object(vm,'_run',return_value=p) as run,patch.object(vm,'info',return_value={}):
   vm.action({'name':'guest','action':'eject'})
   run.assert_called_once_with('dumpxml','guest','--inactive')
