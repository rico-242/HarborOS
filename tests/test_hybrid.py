import sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
from hybrid_layout import layout,mirror_capacity,MIB
from storage import StorageManager
class Error(Exception):
 def __init__(self,message,status=400):super().__init__(message)
class HybridLayoutTests(unittest.TestCase):
 def test_mixed_single_protection_uses_large_pair(self):
  value=layout('hybrid1',[1024*MIB,1024*MIB,2048*MIB,2048*MIB])
  self.assertEqual([t['raid'] for t in value['layers']],['5','1'])
  self.assertEqual(value['capacity'],3296*MIB);self.assertEqual(value['unallocated'],0)
 def test_dual_protection_never_uses_an_unprotected_large_pair(self):
  value=layout('hybrid2',[1024*MIB,1024*MIB,2048*MIB,2048*MIB])
  self.assertEqual(len(value['layers']),1);self.assertEqual(value['capacity'],1520*MIB)
  self.assertEqual(value['unallocated'],2048*MIB)
 def test_dual_large_tier_requires_four_independent_members(self):
  value=layout('hybrid2',[1024*MIB]*2+[2048*MIB]*4)
  self.assertEqual(value['capacity'],5072*MIB)
  self.assertEqual([len(t['members']) for t in value['layers']],[6,4])
  self.assertTrue(all(t['raid']=='6' for t in value['layers']))
 def test_invalid_or_insufficient_disks_rejected(self):
  for level,sizes in [('hybrid2',[1024*MIB]*3),('hybrid1',[1024*MIB]),('hybrid1',[511*MIB]*2),('bad',[1024*MIB]*4)]:
   with self.subTest(level=level,sizes=sizes),self.assertRaises(ValueError):layout(level,sizes)
 def test_mirror_capacity_accounts_for_unbalanced_drives(self):
  self.assertEqual(mirror_capacity([1,1,4]),2);self.assertEqual(mirror_capacity([2,2,2]),3)
class ExpansionGuardTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  self.app=SimpleNamespace(job_progress=Mock(),config={},state=Path(tmp.name),demo=False,lock=threading.RLock(),storage_info=lambda:{'mounted':False},job=lambda title,fn,**kw:fn())
  self.run=Mock(return_value=SimpleNamespace(stdout='{"smart_status":{"passed":true}}',returncode=0))
  self.manager=StorageManager(self.app,self.run,Error)
  self.disks=[dict(id='/dev/disk/by-id/test'+str(i),path='/dev/vd'+str(i),size=1024*MIB,serial='s'+str(i),wwn='',eligible=True) for i in range(4)]
  self.manager.inventory=lambda:self.disks
  self.state={'uuid':'00000000-0000-0000-0000-000000000001','mode':'native-raid1','name':'Pool','sizes':[1024*MIB]*2,'free':512*MIB,'total':1024*MIB}
  self.manager.pool_state=Mock(side_effect=lambda:dict(self.state))
 def plan(self):return self.manager.expand_plan({'disks':[self.disks[0]['id']]})
 def assert_no_writes(self):self.assertFalse(any(c.args[0] in ('wipefs','parted','mdadm','mkfs.btrfs') or c.args[:3]==('btrfs','device','add') for c in self.run.call_args_list))
 def test_exact_acknowledgement_required(self):
  p=self.plan()
  for confirmation,ack in [('Pool',True),('EXPAND Pool',False)]:
   with self.assertRaises(Error):self.manager.expand({'token':p['token'],'confirmation':confirmation,'acknowledge':ack})
  self.assert_no_writes()
 def test_pool_change_rejected_before_writing(self):
  p=self.plan();self.state['uuid']='changed'
  with self.assertRaisesRegex(Error,'pool changed'):self.manager.expand({'token':p['token'],'confirmation':p['confirmation'],'acknowledge':True})
  self.assert_no_writes()
 def test_replaced_disk_rejected_before_writing(self):
  p=self.plan();self.disks[0]['serial']='replaced'
  with self.assertRaisesRegex(Error,'identities changed'):self.manager.expand({'token':p['token'],'confirmation':p['confirmation'],'acknowledge':True})
  self.assert_no_writes()
 def test_creation_and_expansion_tokens_are_not_interchangeable(self):
  p=self.plan()
  with self.assertRaisesRegex(Error,'expired'):self.manager.create({'token':p['token'],'confirmation':'ERASE Pool','acknowledge':True})
  self.assert_no_writes()
 def test_pending_recovery_blocks_planning(self):
  self.manager.pending().write_text('{}')
  with self.assertRaisesRegex(Error,'recovery'):self.plan()
  self.assert_no_writes()
 def test_old_partition_preflight_requests_tree_and_blocks_active_holders(self):
  import json
  part={'path':'/dev/vd01','type':'part','mountpoints':[None]}
  tree={'blockdevices':[{'path':'/dev/vd0','type':'disk','mountpoints':[None],'children':[part]}]}
  self.run.return_value=SimpleNamespace(stdout=json.dumps(tree),returncode=0)
  with patch('hybrid_storage.shutil.which',return_value='/tool'):
   self.assertEqual(self.manager.array_preflight(self.disks[:1]),['/dev/vd01'])
   self.assertIn('--tree',self.run.call_args.args)
   part['children']=[{'path':'/dev/md0','type':'raid1','mountpoints':[None]}]
   self.run.return_value.stdout=json.dumps(tree)
   with self.assertRaisesRegex(Error,'active storage'):self.manager.array_preflight(self.disks[:1])
  self.assert_no_writes()
 def test_missing_partitioning_tools_rejected_before_writes(self):
  with patch('hybrid_storage.shutil.which',return_value=None):
   with self.assertRaisesRegex(Error,'tools are missing'):self.manager.array_preflight(self.disks)
  self.run.assert_not_called()
 def test_dual_expansion_requires_four_new_disks(self):
  self.state['mode']='hybrid2'
  with self.assertRaises(Error):self.plan()
  self.assert_no_writes()
if __name__=='__main__':unittest.main()
