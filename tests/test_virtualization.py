import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / 'harbor'))
from virtualization import Virtualization, PACKAGES

class FakeApp:
    def job_progress(self,*args): pass
    def job(self,title,fn,**kwargs): return {'title':title,'result':fn()}

class VirtualizationTests(unittest.TestCase):
    def test_package_allowlist(self):
        self.assertEqual(PACKAGES, ('qemu-system-x86','qemu-utils','libvirt-daemon-system','libvirt-daemon-config-network','libvirt-clients','virtinst','dnsmasq-base'))
    def test_status_shape(self):
        with patch('virtualization.subprocess.run', return_value=type('P',(),{'stdout':'inactive'})()):
            state=Virtualization(FakeApp(),None,ValueError).status()
        self.assertIn('ready',state); self.assertIn('kvm',state); self.assertIn('services',state)

if __name__ == '__main__': unittest.main()
