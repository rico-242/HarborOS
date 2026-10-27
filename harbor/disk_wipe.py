"""Confirmed quick wipes of non-pool disks, independent of SMART health."""
import hashlib,json,os,re,secrets,time
from pathlib import Path

def nodes(tree):
 for node in tree:
  yield node
  yield from nodes(node.get('children',[]))

def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

class DiskWipe:
 def wipe_inspect(self,identifier):
  if self.app.demo or os.getenv('HARBOR_LIVE')=='1':raise self.error('Install Harbour before wiping disks.',409)
  disk=next((d for d in self.inventory() if d['id']==identifier),None)
  if not disk or not identifier.startswith('/dev/disk/by-id/') or not disk['serial']:raise self.error('A connected disk with a stable ID and serial is required.',409)
  config=self.app.config.get('storage',{});reserved=list(config.get('disks',[]))
  for group in config.get('hybrid',{}).get('groups',[]):reserved.extend(group.get('disks',[]));reserved.extend(a['path'] for a in group.get('arrays',[]))
  protected={str(Path(p).resolve()) for p in reserved}
  if identifier in reserved or str(Path(disk['path']).resolve()) in protected:raise self.error('Current pool members cannot be wiped. Use Replace drive first.',409)
  fields='PATH,TYPE,SIZE,SERIAL,WWN,RO,FSTYPE,UUID,PARTUUID,MOUNTPOINTS'
  tree=json.loads(self.run('lsblk','-J','-b','--tree','-p','-o',fields,identifier).stdout)['blockdevices'];items=list(nodes(tree))
  if len(tree)!=1 or tree[0]['type']!='disk' or str(Path(tree[0]['path']).resolve())!=str(Path(disk['path']).resolve()):raise self.error('The disk topology could not be verified.',409)
  if any(str(Path(n['path']).resolve()) in protected or (config.get('uuid') and n.get('uuid')==config['uuid']) for n in items):raise self.error('Current pool members cannot be wiped. Use Replace drive first.',409)
  # Check all mounted Btrfs members; lsblk only shows the mount on one member.
  mounted=self.run('btrfs','filesystem','show','--mounted','--raw',check=False)
  members={str(Path(p).resolve()) for p in re.findall(r'\bpath\s+(/dev/\S+)',mounted.stdout)}
  if mounted.returncode:
   try:uncertain=any(' - btrfs ' in line for line in Path('/proc/self/mountinfo').read_text().splitlines())
   except OSError:uncertain=True
   if uncertain and any(n.get('fstype')=='btrfs' for n in items):raise self.error('Mounted Btrfs membership could not be verified.',409)
  arrays=[];allowed={'disk','part','raid0','raid1','raid4','raid5','raid6','raid10','linear','md'}
  def check(values):
   for n in values:
    if n.get('type') not in allowed:raise self.error('Unknown active storage layer. Detach it before wiping.',409)
    if any(n.get('mountpoints') or []) or n.get('fstype')=='swap' or str(Path(n['path']).resolve()) in members:raise self.error('Mounted or system disks cannot be wiped. Unmount external volumes first.',409)
    if n.get('ro'):raise self.error('This disk or an attached storage layer is read-only.',409)
    if str(Path(n['path']).resolve()) in protected or (config.get('uuid') and n.get('uuid')==config['uuid']):raise self.error('The disk is connected to the current pool.',409)
  check(items)
  for path in sorted({n['path'] for n in items if n.get('type','').startswith('raid') or n.get('type') in ('linear','md')}):
   ancestry=list(nodes(json.loads(self.run('lsblk','-s','-J','-b','-p','-o',fields,path).stdout)['blockdevices']));check(ancestry)
   if len({n['path'] for n in ancestry if n.get('type','').startswith('raid') or n.get('type') in ('linear','md')})!=1:raise self.error('Nested RAID arrays require manual detachment.',409)
   detail=self.run('mdadm','--detail','--export',path,check=False).stdout
   match=re.search(r'^MD_UUID=(\S+)$',detail,re.M)
   uuids=set()
   for member in {n['path'] for n in ancestry if n['type'] in ('disk','part') and n.get('fstype')=='linux_raid_member'}:
    report=self.run('mdadm','--examine','--export',member,check=False).stdout
    found=re.search(r'^MD_UUID=(\S+)$',report,re.M)
    if found:uuids.add(found[1])
   if match:uuids.add(match[1])
   if len(uuids)!=1:raise self.error('The old RAID identity could not be verified.',409)
   uuid=next(iter(uuids))
   if uuid in {a.get('uuid') for group in config.get('hybrid',{}).get('groups',[]) for a in group.get('arrays',[])}:raise self.error('The old array belongs to the current pool.',409)
   arrays.append({'path':path,'uuid':uuid,'members':sorted(n['path'] for n in ancestry if n['type']=='disk')})
  known={Path(a['path']).resolve().name for a in arrays}
  for n in items:
   for holder in (Path('/sys/class/block')/Path(n['path']).name/'holders').glob('*'):
    if holder.name not in known:raise self.error('An unrecognized holder is using this disk.',409)
  parts=[{k:n.get(k) for k in ('path','size','partuuid','uuid','fstype')} for n in items if n['type']=='part']
  identity={k:disk[k] for k in ('id','path','size','serial','wwn')}
  return {'disk':disk,'identity':identity,'partitions':parts,'arrays':arrays,'raid_members':[n['path'] for n in items if n.get('fstype')=='linux_raid_member' and n['type'] in ('disk','part')]}

 def wipe_inventory(self):
  result=[]
  for disk in self.inventory():
   item=dict(disk)
   try:self.wipe_inspect(disk['id']);item.update(wipe_allowed=True,wipe_reason='')
   except Exception as error:item.update(wipe_allowed=False,wipe_reason=str(error))
   result.append(item)
  return result

 def wipe_plan(self,data):
  self.check_pending();state=self.wipe_inspect(data.get('disk'));token=secrets.token_urlsafe(24)
  self.plans={k:v for k,v in self.plans.items() if v['expires']>time.monotonic()}
  if len(self.plans)>=20:self.plans.pop(next(iter(self.plans)))
  confirmation='WIPE '+state['disk']['serial']
  self.plans[token]={'kind':'wipe','expires':time.monotonic()+300,'state':state,'confirmation':confirmation}
  return {'token':token,'disk':state['disk'],'arrays':state['arrays'],'confirmation':confirmation,
   'warning':'All partitions, filesystem and RAID signatures on this disk will be removed. This is not a secure data erase and does not repair disk health.'}

 def wipe_disk(self,data):
  with self.app.lock:
   plan=self.plans.get(data.get('token',''))
   if not plan or plan.get('kind')!='wipe' or plan['expires']<time.monotonic():raise self.error('The wipe plan expired. Review the disk again.',409)
   if data.get('confirmation')!=plan['confirmation'] or data.get('acknowledge') is not True:raise self.error('Confirm wiping using the exact disk serial.')
   self.check_pending();plan=self.plans.pop(data['token'])
   # Reserve the storage operation before queuing, so competing operations fail closed.
   self.record({'kind':'wipe','stage':'queued','disk':plan['state']['identity']})
  def execute():
   self.app.job_progress('Checking disk','Rechecking identity, mounts and current pool membership. SMART health does not block wiping.')
   expected=plan['state'];current=self.wipe_inspect(expected['disk']['id'])
   if fingerprint(current)!=fingerprint(expected):raise self.error('Disk identity or storage topology changed. Review the disk again.',409)
   self.record({'kind':'wipe','stage':'detaching','disk':expected['identity'],'arrays':current['arrays']})
   for array in current['arrays']:
    self.app.job_progress('Detaching old RAID','Stopping the unused array '+array['path']+'. Only the selected disk will be wiped.')
    self.run('mdadm','--stop',array['path'],timeout=60)
   self.run('udevadm','settle',timeout=30)
   current=self.wipe_inspect(expected['disk']['id'])
   if current['identity']!=expected['identity'] or current['partitions']!=expected['partitions'] or current['arrays']:raise self.error('Disk topology changed after detaching. Wiping stopped.',409)
   self.record({'kind':'wipe','stage':'wiping','disk':expected['identity']})
   self.app.job_progress('Wiping signatures','Removing RAID and filesystem signatures from the confirmed disk.')
   for member in current['raid_members']:self.run('mdadm','--zero-superblock',member,timeout=30)
   for part in reversed(current['partitions']):self.run('wipefs','--all','--force',part['path'],timeout=60)
   self.run('wipefs','--all','--force',expected['disk']['id'],timeout=60)
   self.run('blockdev','--rereadpt',expected['disk']['id'],timeout=30)
   self.run('udevadm','settle',timeout=30)
   self.app.job_progress('Verifying disk','Checking that partitions and recognized signatures are gone.')
   final=self.wipe_inspect(expected['disk']['id'])
   signatures=json.loads(self.run('wipefs','--json',expected['disk']['id']).stdout).get('signatures',[])
   if final['identity']!=expected['identity'] or final['partitions'] or final['arrays'] or signatures:raise self.error('The disk did not wipe completely. Review its health and the storage journal.',409)
   self.pending().unlink();self.app.event('Disk wiped: '+expected['disk']['serial'])
   return {'disk':expected['disk']['id'],'wiped':True}
  return self.app.job('Wipe drive',execute,kind='storage',target=plan['state']['disk']['serial'])
