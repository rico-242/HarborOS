import copy,json,sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
from storage import StorageManager
class Error(Exception):
 def __init__(self,message,status=400):super().__init__(message)
class WipeTests(unittest.TestCase):
 def setUp(self):
  root=Path(__file__).resolve().parents[1]/'.local/tests';root.mkdir(parents=True,exist_ok=True)
  temp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(temp.cleanup)
  self.app=SimpleNamespace(demo=False,state=Path(temp.name),config={'storage':{'uuid':'POOL','disks':['/dev/current-pool']}},lock=threading.RLock(),job=lambda title,fn,**kw:fn(),job_progress=Mock(),event=Mock())
  self.disk={'id':'/dev/disk/by-id/ata-spare','path':'/dev/vdb','size':1000000,'serial':'SPARE','wwn':'','model':'Spare','eligible':False,'reason':'Active old array','existing_data':True}
  self.array_type='raid1';self.array=True;self.wiped=False;self.mounts=[];self.ancestry_mounts=[];self.calls=[]
  self.manager=StorageManager(self.app,self.command,Error);self.manager.inventory=lambda:[self.disk]
  self.manager.health=Mock(side_effect=Error('Failed SMART'))
  self.manager.record=lambda value:self.manager.pending().write_text(json.dumps(value))
 def tree(self,ancestry=False):
  disk={'path':'/dev/vdb','type':'disk','size':1000000,'ro':False,'mountpoints':self.mounts}
  if not self.wiped:
   part={'path':'/dev/vdb1','type':'part','size':990000,'partuuid':'PART','uuid':'OLD','fstype':'linux_raid_member','mountpoints':[]};disk['children']=[part]
   if self.array:part['children']=[{'path':'/dev/md127','type':self.array_type,'uuid':'OLD-FS','mountpoints':self.ancestry_mounts}]
  return {'blockdevices':[disk]}
 def command(self,*args,**kwargs):
  self.calls.append(args);out=''
  if args[0]=='lsblk':out=json.dumps(self.tree('-s' in args))
  if args[:3]==('btrfs','filesystem','show'):out=''
  if args[:3]==('mdadm','--detail','--export'):out='' if self.array_type=='md' else 'MD_UUID=OLD-ARRAY\n'
  if args[:3]==('mdadm','--examine','--export'):out='MD_UUID=OLD-ARRAY\n'
  if args[:2]==('mdadm','--stop'):self.array=False
  if args[:3]==('wipefs','--all','--force') and args[-1]==self.disk['id']:self.wiped=True
  if args[:2]==('wipefs','--json'):out='{"signatures":[]}'
  return SimpleNamespace(stdout=out,returncode=0)
 def plan(self):return self.manager.wipe_plan({'disk':self.disk['id']})
 def execute(self,plan):return self.manager.wipe_disk({'token':plan['token'],'confirmation':plan['confirmation'],'acknowledge':True})
 def destructive(self):return [c for c in self.calls if c[:2] in (('mdadm','--stop'),('mdadm','--zero-superblock')) or c[:2]==('wipefs','--all')]
 def test_failed_health_does_not_block_wipe_and_only_selected_disk_is_erased(self):
  result=self.execute(self.plan());self.assertTrue(result['wiped']);self.manager.health.assert_not_called()
  self.assertEqual(self.destructive(),[('mdadm','--stop','/dev/md127'),('mdadm','--zero-superblock','/dev/vdb1'),('wipefs','--all','--force','/dev/vdb1'),('wipefs','--all','--force',self.disk['id'])]);self.assertFalse(self.manager.pending().exists())
 def test_current_pool_member_cannot_be_wiped_even_unmounted(self):
  self.app.config['storage']['disks']=[self.disk['id']]
  with self.assertRaisesRegex(Error,'pool'):self.plan()
  self.assertFalse(self.destructive())
 def test_system_or_mounted_disk_cannot_be_wiped(self):
  self.mounts=['/']
  with self.assertRaisesRegex(Error,'Mounted'):self.plan()
  self.assertFalse(self.destructive())
 def test_mounted_old_array_cannot_be_stopped(self):
  self.ancestry_mounts=['/external']
  with self.assertRaisesRegex(Error,'Mounted'):self.plan()
  self.assertFalse(self.destructive())
 def test_wrong_confirmation_and_missing_ack_never_queue(self):
  plan=self.plan()
  for text,ack in [('WIPE wrong',True),('WIPE SPARE',False)]:
   with self.assertRaisesRegex(Error,'Confirm'):self.manager.wipe_disk({'token':plan['token'],'confirmation':text,'acknowledge':ack})
  self.assertFalse(self.manager.pending().exists());self.assertFalse(self.destructive())
 def test_changed_disk_after_review_never_touched(self):
  plan=self.plan();self.disk['serial']='REPLACED'
  with self.assertRaisesRegex(Error,'changed'):self.execute(plan)
  self.assertFalse(self.destructive());self.assertTrue(self.manager.pending().exists())
 def test_new_mount_after_review_never_touched(self):
  plan=self.plan();self.mounts=['/external']
  with self.assertRaisesRegex(Error,'Mounted'):self.execute(plan)
  self.assertFalse(self.destructive())
 def test_array_stop_failure_never_wipes(self):
  plan=self.plan();original=self.manager.run
  def run(*args,**kwargs):
   if args[:2]==('mdadm','--stop'):raise Error('Busy old array')
   return original(*args,**kwargs)
  self.manager.run=run
  with self.assertRaisesRegex(Error,'Busy'):self.execute(plan)
  self.assertFalse(self.wiped);self.assertTrue(self.manager.pending().exists())
 def test_expired_plan_and_competing_operation_rejected(self):
  plan=self.plan();self.manager.plans[plan['token']]['expires']=time.monotonic()-1
  with self.assertRaisesRegex(Error,'expired'):self.execute(plan)
  self.manager.record({'kind':'other'})
  with self.assertRaisesRegex(Error,'recovery'):self.plan()
 def test_unknown_holders_block_wipe(self):
  with patch.object(Path,'glob',return_value=iter([Path('dm-0')])):
   with self.assertRaisesRegex(Error,'unrecognized'):self.plan()
  self.assertFalse(self.destructive())
 def test_wipe_token_cannot_create_a_pool(self):
  plan=self.plan()
  with self.assertRaisesRegex(Error,'expired'):self.manager.create({'token':plan['token'],'acknowledge':True,'confirmation':plan['confirmation']})
  self.assertFalse(self.destructive())

 def test_inactive_md_array_can_be_detached_and_wiped(self):
  self.array_type='md'
  self.assertTrue(self.execute(self.plan())['wiped'])
  self.manager.health.assert_not_called()
 def test_unidentified_inactive_array_is_never_stopped(self):
  self.array_type='md';original=self.manager.run
  def command(*args,**kwargs):
   if args[:3]==('mdadm','--examine','--export'):return SimpleNamespace(stdout='',returncode=1)
   return original(*args,**kwargs)
  self.manager.run=command
  with self.assertRaisesRegex(Error,'identity'):self.plan()
  self.assertFalse(self.destructive())
