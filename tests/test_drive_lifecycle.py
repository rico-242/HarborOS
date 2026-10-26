import copy,json,sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
from storage import StorageManager
from hybrid_layout import MIB
class Error(Exception):
 def __init__(self,message,status=400):super().__init__(message)
class DriveLifecycleTests(unittest.TestCase):
 def setUp(self):
  root=Path(__file__).resolve().parents[1]/'.local/tests';root.mkdir(parents=True,exist_ok=True)
  tmp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(tmp.cleanup)
  self.app=SimpleNamespace(state=Path(tmp.name),demo=False,config={'storage':{'disks':['old']}},lock=threading.RLock(),job=lambda title,fn,**kw:fn(),job_progress=Mock())
  self.run=Mock();self.manager=StorageManager(self.app,self.run,Error)
  self.member=dict(id='1',disk_id='old',label='Mirror-1',path='/dev/vdb',missing=False,size=1024*MIB,minimum=1024*MIB)
  self.state=dict(uuid='00000000-0000-0000-0000-000000000001',mode='native-raid1',members=[self.member,dict(self.member,id='2',disk_id='other')],profiles={'Data':'RAID1','Metadata':'RAID1','System':'RAID1'},free=700*MIB,total=1024*MIB,used=30*MIB)
  self.manager.lifecycle_state=lambda:copy.deepcopy(self.state)
  self.target=dict(id='spare',path='/dev/vdc',size=1024*MIB,serial='spare-serial',wwn='',eligible=True)
  self.manager.inventory=lambda:[self.target]
  self.manager.health=Mock(return_value=[]);self.manager.array_preflight=Mock(return_value=[])
 def plan(self,operation='replace'):
  return self.manager.lifecycle_plan(dict(operation=operation,member='1',target='spare'))
 def test_two_member_mirror_cannot_be_reduced_to_one(self):
  with self.assertRaisesRegex(Error,'reduce protection'):self.plan('remove')
  self.run.assert_not_called()
 def test_replacement_cannot_reuse_logical_member_even_if_currently_unused(self):
  self.app.config['storage']['disks'].append('spare')
  with self.assertRaisesRegex(Error,'already recorded'):self.plan()
  self.run.assert_not_called()
 def test_small_spare_rejected_before_write(self):
  self.target['size']-=1
  with self.assertRaisesRegex(Error,'too small'):self.plan()
  self.run.assert_not_called()
 def test_exact_confirmation_and_acknowledgement_required(self):
  p=self.plan()
  for text,ack in [('REPLACE other',True),(p['confirmation'],False)]:
   with self.assertRaisesRegex(Error,'Confirm'):self.manager.lifecycle_action(dict(token=p['token'],confirmation=text,acknowledge=ack))
  self.run.assert_not_called();self.assertFalse(self.manager.pending().exists())
 def test_changed_disk_after_plan_is_not_erased(self):
  p=self.plan();self.target['serial']='different'
  with self.assertRaisesRegex(Error,'identity changed'):self.manager.lifecycle_action(dict(token=p['token'],confirmation=p['confirmation'],acknowledge=True))
  self.run.assert_not_called();self.assertFalse(self.manager.pending().exists())
 def test_membership_change_during_slow_health_check_is_rejected(self):
  p=self.plan();self.manager.health.side_effect=lambda disks:self.state['members'].append(dict(self.member,id='3'))
  with self.assertRaisesRegex(Error,'membership changed'):self.manager.lifecycle_action(dict(token=p['token'],confirmation=p['confirmation'],acknowledge=True))
  self.run.assert_not_called();self.assertFalse(self.manager.pending().exists())
 def test_pending_repair_blocks_another_plan(self):
  self.manager.pending().write_text('{}')
  with self.assertRaisesRegex(Error,'recovery'):self.plan()
  self.run.assert_not_called()
 def test_expired_plan_is_rejected(self):
  p=self.plan();self.manager.plans[p['token']]['expires']=time.monotonic()-1
  with self.assertRaisesRegex(Error,'expired'):self.manager.lifecycle_action(dict(token=p['token'],confirmation=p['confirmation'],acknowledge=True))
  self.run.assert_not_called()
 def test_resume_requires_original_target_identity(self):
  p=self.plan();plan=self.manager.plans[p['token']]
  self.manager.pending().write_text(json.dumps(dict(kind='member',stage='prepared',plan=plan)));self.app.jobs={}
  self.target['serial']='different'
  with self.assertRaisesRegex(Error,'absent or changed'):self.manager.lifecycle_resume(dict(confirmation='RESUME REPAIR',acknowledge=True))
  self.run.assert_not_called()
