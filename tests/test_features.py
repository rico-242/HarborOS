import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
import appstore
import storage


class Error(Exception):
    def __init__(self,message,status=400):
        super().__init__(message)


class CatalogTests(unittest.TestCase):
    def test_catalog_snapshot_and_icon_confinement(self):
        self.assertGreater(len(appstore.OFFICIAL),100)
        self.assertEqual(appstore.CATALOG_INFO['license'],'Apache-2.0')
        self.assertEqual(len({appstore.project_name(i) for i in appstore.OFFICIAL}),len(appstore.OFFICIAL))
        for ident,item in appstore.OFFICIAL.items():
            self.assertNotIn('/',ident)
            if item['icon']:
                self.assertTrue(item['icon'].startswith('/catalog/icons/'))
                self.assertTrue((appstore.CATALOG_ROOT/item['icon'].removeprefix('/catalog/')).is_file())

    def test_compose_translates_data_and_preserves_multi_service(self):
        plan=appstore.prepare('jellyfin','/srv/harbor/apps','/srv/harbor/storage')
        self.assertTrue(plan['compose']['services'])
        encoded=json.dumps(plan['compose'])
        self.assertNotIn('/DATA',encoded)
        self.assertNotIn('$AppID',encoded)
        self.assertNotIn('container_name',encoded)
        self.assertIn('/srv/harbor/apps/jellyfin',encoded)

    def test_settings_cannot_add_environment_or_inject_compose_expansion(self):
        with self.assertRaisesRegex(ValueError,'Unknown application setting'):
            appstore.prepare('jellyfin','/apps','/storage',options={'environment':{'x.EVIL':'bad'}})
        self.assertEqual(appstore.expand('${PUID}-${TZ:-UTC}-$AppID',{'PUID':1000,'AppID':'example'}),'1000-UTC-example')
        self.assertEqual(appstore.expand('$(touch /tmp/no)',{}),'$$(touch /tmp/no)')


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.app=type('App',(),{})()
        self.app.demo=False
        self.app.config={}
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.app.state=Path(temporary.name)
        self.app.lock=threading.RLock()
        self.app.storage_info=lambda:{'mounted':False}
        self.app.job=lambda title,action,**metadata:action()
        self.app.job_progress=lambda *args:None
        self.manager=storage.StorageManager(self.app,lambda *args,**kwargs:type('Result',(),{'stdout':'{"smart_status":{"passed":true}}'})(),Error)
        self.disks=[{'id':'/dev/disk/by-id/virtio-test'+str(i),'path':'/dev/vd'+chr(98+i),'serial':'test'+str(i),'size':1000,'wwn':'','eligible':True} for i in range(2)]
        self.manager.inventory=lambda:self.disks

    def test_capacity_and_minimum_disks(self):
        self.assertEqual(storage.capacity('1',[1000,2000]),1000)
        self.assertEqual(storage.capacity('5',[1000,1000,1000]),2000)
        self.assertEqual(storage.capacity('6',[1000]*4),2000)
        self.assertEqual(storage.capacity('10',[1000]*4),2000)
        self.assertEqual(storage.capacity('linear',[1000,2000]),3000)
        for level,sizes in [('5',[1000]*2),('6',[1000]*3),('10',[1000]*5),('1',[1000]*3)]:
            with self.assertRaises(ValueError):storage.capacity(level,sizes)

    def plan(self):
        return self.manager.plan({'name':'Test','level':'1','disks':[d['id'] for d in self.disks]})

    def test_in_use_and_duplicate_disks_rejected(self):
        self.disks[0]['eligible']=False
        with self.assertRaisesRegex(Error,'protected'):self.plan()
        with self.assertRaises(Error):self.manager.selection([self.disks[1]['id']]*2,'1')

    def test_secondary_btrfs_member_is_protected(self):
        self.manager.inventory=storage.StorageManager.inventory.__get__(self.manager)
        device={'type':'disk','path':'/dev/vdb','size':1000,'ro':False,'mountpoints':[],
                'children':[{'path':'/dev/vdb1','fstype':'btrfs','mountpoints':[]}]}
        def run(*args,**kwargs):
            output=json.dumps({'blockdevices':[device]}) if args[0]=='lsblk' else 'devid 2 size 1000 used 0 path /dev/vdb1\n'
            return type('Result',(),{'stdout':output,'returncode':0})()
        self.manager.run=run
        self.assertEqual(self.manager.inventory()[0]['reason'],'Mounted disk, operating system, or active storage')

    def test_unused_btrfs_signature_remains_available_without_mounted_btrfs(self):
        self._check_failed_btrfs_discovery('', 'No stable disk identifier')

    def test_failed_discovery_protects_btrfs_when_any_btrfs_is_mounted(self):
        self._check_failed_btrfs_discovery('42 1 0:3 / /data rw - btrfs /dev/vdc rw', 'Mounted disk, operating system, or active storage')

    def _check_failed_btrfs_discovery(self, mountinfo, reason):
        self.manager.inventory=storage.StorageManager.inventory.__get__(self.manager)
        device={'type':'disk','path':'/dev/vdb','size':1000,'ro':False,'mountpoints':[], 'fstype':'btrfs'}
        def run(*args,**kwargs):
            return type('Result',(),{'stdout':json.dumps({'blockdevices':[device]}) if args[0]=='lsblk' else '', 'returncode':0 if args[0]=='lsblk' else 1})()
        self.manager.run=run
        original=Path.read_text
        def read(path,*args,**kwargs):
            return mountinfo if path.as_posix()=='/proc/self/mountinfo' else original(path,*args,**kwargs)
        with patch.object(Path,'read_text',read):self.assertEqual(self.manager.inventory()[0]['reason'],reason)

    def test_typed_confirmation_and_identity_revalidation(self):
        plan=self.plan()
        with self.assertRaisesRegex(Error,'Confirm erasure'):
            self.manager.create({'token':plan['token'],'confirmation':'Test','acknowledge':True})
        self.disks[0]['serial']='replaced-disk'
        with self.assertRaisesRegex(Error,'identities changed'):
            self.manager.create({'token':plan['token'],'confirmation':'ERASE Test','acknowledge':True})

    def test_old_creation_token_cannot_bypass_interrupted_operation_guard(self):
        plan=self.plan()
        self.manager.pending().write_text('{}')
        with self.assertRaisesRegex(Error,'recovery'):
            self.manager.create({'token':plan['token'],'confirmation':'ERASE Test','acknowledge':True})

    def test_existing_storage_and_failed_health_rejected(self):
        self.app.storage_info=lambda:{'mounted':True}
        with self.assertRaisesRegex(Error,'already exists'):self.plan()
        self.app.storage_info=lambda:{'mounted':False}
        self.manager.run=lambda *args,**kwargs:type('Result',(),{'stdout':'{"smart_status":{"passed":false}}'})()
        with self.assertRaisesRegex(Error,'failing health'):self.plan()


if __name__=='__main__':unittest.main()

