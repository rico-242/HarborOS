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
