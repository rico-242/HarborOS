import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'harbor'))
from drive_health import assessment
from storage import StorageManager


class Error(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)


class HealthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.app = SimpleNamespace(config={}, demo=False, state=Path(temp.name),
            lock=threading.RLock(), storage_info=lambda: {'mounted': False})
        self.run = Mock(return_value=SimpleNamespace(stdout=json.dumps({
            'smart_status': {'passed': True}, 'ata_smart_attributes': {'table': [
                {'id': 197, 'raw': {'value': 8}}]}})))
        self.manager = StorageManager(self.app, self.run, Error)
        self.disks = [dict(id='/dev/disk/by-id/test'+str(i), path='/dev/vd'+str(i),
            serial='SERIAL'+str(i), size=1024**3, eligible=True) for i in range(2)]
        self.manager.inventory = lambda: self.disks
        self.manager.refresh_health = Mock()

    def test_each_sector_counter_warns_even_with_overall_smart_pass(self):
        for attribute in (5, 187, 197, 198):
            report = {'smart_status': {'passed': True}, 'ata_smart_attributes': {
                'table': [{'id': attribute, 'raw': {'value': 1}}]}}
            self.assertEqual(assessment(report)['health'], 'failing')
            report['ata_smart_attributes']['table'][0]['raw']['value'] = 0
            self.assertEqual(assessment(report)['health'], 'healthy')

    def test_nvme_failure_media_errors_and_exhausted_endurance_warn(self):
        for value in ({'critical_warning': 1}, {'media_errors': 3}, {'percentage_used': 100}):
            self.assertEqual(assessment({'nvme_smart_health_information_log': value})['health'], 'failing')

    def test_missing_or_unreadable_health_is_unknown(self):
        for value in ({}, [], None):
            self.assertEqual(assessment(value)['health'], 'unknown')
        self.run.side_effect = TimeoutError('timeout')
        self.assertEqual(self.manager.health(self.disks), [d['id'] for d in self.disks])

    def test_failing_disks_can_be_reviewed_for_clean_pool_creation(self):
        plan = self.manager.plan({'name': 'Pool', 'level': 'hybrid1',
                                  'disks': [d['id'] for d in self.disks]})
        self.assertEqual(len(plan['health_warnings']), 2)
        self.assertEqual(plan['health_warnings'][0]['serial'], 'SERIAL0')
        self.assertTrue(all(d['eligible'] and d['health'] == 'failing' for d in plan['disks']))
        self.manager.create_hybrid = Mock(return_value='accepted')
        self.assertEqual(self.manager.create(dict(token=plan['token'],
            confirmation=plan['confirmation'], acknowledge=True)), 'accepted')

    def test_failing_disks_can_be_reviewed_for_expansion(self):
        self.manager.pool_state = Mock(return_value=dict(uuid='pool', mode='native-raid1',
            name='Pool', sizes=[1024**3]*2, free=1024**3, total=2*1024**3))
        plan = self.manager.expand_plan({'disks': [self.disks[0]['id']]})
        self.assertEqual(plan['health_warnings'][0]['reasons'], ['8 pending sectors'])

    def test_protected_disks_still_cannot_be_selected(self):
        self.disks[0]['eligible'] = False
        with self.assertRaisesRegex(Error, 'protected'):
            self.manager.selection([self.disks[0]['id']], 'basic')
        self.run.assert_not_called()

    def test_only_failing_pool_members_mark_the_pool_at_risk(self):
        self.manager.health(self.disks)
        self.assertFalse(self.manager.pool_health()['health_risk'])
        self.app.config['storage'] = {'disks': [self.disks[1]['id']]}
        risk = self.manager.pool_health()
        self.assertTrue(risk['health_risk'])
        self.assertEqual([d['serial'] for d in risk['failing_drives']], ['SERIAL1'])

    def test_cache_never_attaches_previous_drive_health_to_replacement(self):
        self.manager.health(self.disks)
        replacement = dict(self.disks[0], serial='NEW-SERIAL')
        self.manager.cached_health([replacement])
        self.assertEqual(replacement['health'], 'checking')
        self.assertEqual(replacement['health_reasons'], [])

    def test_cached_listing_does_not_repeat_smart_commands(self):
        self.manager.health(self.disks)
        self.run.reset_mock()
        self.manager.cached_health(self.disks)
        self.manager.pool_health()
        self.run.assert_not_called()
        self.assertEqual(self.disks[0]['health'], 'failing')


if __name__ == '__main__':
    unittest.main()
