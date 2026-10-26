import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
import appstore

class JellyfinHardwareTests(unittest.TestCase):
    def plan(self,present):
        with patch('appstore.Path.exists',lambda path:path.as_posix() in present):
            return appstore.prepare('jellyfin','/apps','/storage')

    def test_missing_optional_hardware_uses_software_without_mutating_catalog(self):
        original=copy.deepcopy(appstore.OFFICIAL['jellyfin'])
        plan=self.plan(set());service=plan['compose']['services']['jellyfin']
        self.assertNotIn('devices',service)
        self.assertEqual({v['target'] for v in service['volumes']},{'/config','/Media'})
        self.assertFalse(plan['warnings']);self.assertTrue(plan['compatibility'])
        self.assertEqual(appstore.OFFICIAL['jellyfin'],original)

    def test_available_gpu_retained_but_missing_pi_mappings_omitted(self):
        plan=self.plan({'/dev/dri'});service=plan['compose']['services']['jellyfin']
        self.assertEqual(service['devices'],['/dev/dri:/dev/dri'])
        self.assertTrue(any('direct hardware' in warning for warning in plan['warnings']))
        self.assertFalse(any('/opt/vc/lib' in warning for warning in plan['warnings']))

    def test_present_optional_hardware_preserved(self):
        plan=self.plan(appstore.JELLYFIN_OPTIONAL_DEVICES|{'/opt/vc/lib'})
        self.assertEqual(len(plan['compose']['services']['jellyfin']['devices']),6)
        self.assertTrue(any(v['source']=='/opt/vc/lib' for v in plan['compose']['services']['jellyfin']['volumes']))
        self.assertFalse(plan['compatibility'])

    def test_unknown_mounts_and_devices_never_silently_omitted(self):
        service={'devices':['/dev/required:/dev/required','/dev/dri:/different'],
                 'volumes':[{'type':'bind','source':'/required','target':'/required'},'/opt/vc/lib:/different:ro']}
        original=copy.deepcopy(service)
        with patch('appstore.Path.exists',return_value=False):appstore.jellyfin_hardware(service)
        self.assertEqual(service,original)

if __name__=='__main__':unittest.main()
