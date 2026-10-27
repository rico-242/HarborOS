"""Owner-confirmed member replacement and evacuation. Never downgrade profiles."""
import copy,json,os,re,secrets,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from hybrid_layout import HYBRID_LEVELS,MIB,mirror_capacity

class DriveLifecycle:
 def recover_mount(self,data):
  if self.app.demo or os.getenv('HARBOR_LIVE')=='1':raise self.error('Install Harbour before repairing storage.',409)
  if self.pending().exists():
   journal=json.loads(self.pending().read_text())
   if journal.get('kind')!='member' or not self.recovery_pending():self.check_pending()
  if self.app.storage_info()['mounted']:return {'mounted':True}
  config=self.app.config.get('storage',{});uuid=config.get('uuid','')
  if not re.fullmatch(r'[a-fA-F0-9-]{36}',uuid):raise self.error('The saved pool UUID is unavailable. Manual pool identification is required.',409)
  if data.get('confirmation')!='MOUNT DEGRADED' or data.get('acknowledge') is not True:raise self.error('Confirm mounting the existing pool with reduced protection.',409)
  # The kernel enforces whether enough redundant copies survive. Never force an
  # array, format a device, or persist the degraded option in normal boot config.
  self.run('systemd-run','--wait','--pipe','--collect','--unit=harbor-repair-mount','/usr/bin/mount','-t','btrfs','-o','degraded','UUID='+uuid,str(self.app.storage),timeout=120)
  return self.lifecycle_info()

 def lifecycle_state(self):
  if self.app.demo or os.getenv('HARBOR_LIVE')=='1':raise self.error('Install Harbour before managing pool members.',409)
  info=self.app.storage_info()
  if not info['mounted'] or info.get('filesystem')!='btrfs':raise self.error('Mount the existing Btrfs pool before managing its members. Do not create a new pool over existing data.',409)
  mount=str(self.app.storage)
  show=self.run('btrfs','filesystem','show','--raw',mount).stdout
  match=re.search(r'uuid:\s*([a-fA-F0-9-]{36})',show)
  if not match:raise self.error('The pool identity could not be verified.',409)
  uuid=match[1];config=self.app.config.get('storage',{});level=config.get('level')
  if config.get('uuid') and config['uuid']!=uuid:raise self.error('The mounted pool differs from the saved pool.',409)
  usage=self.run('btrfs','filesystem','usage','-b',mount).stdout
  profiles=dict(re.findall(r'^(Data|Metadata|System),([^:]+):',usage,re.M))
  devices=[{'devid':int(n),'size':int(size),'path':path} for n,size,path in re.findall(r'devid\s+(\d+)\s+size\s+(\d+)\s+used\s+\d+\s+path\s+(\S+)',show)]
  inventory=self.inventory();members=[];arrays=[]
  if level in HYBRID_LEVELS:
   if profiles.get('Data')!='single' or profiles.get('Metadata')!='DUP':raise self.error('The Hybrid filesystem profiles changed. Manual review is required.',409)
   groups=config.get('hybrid',{}).get('groups',[])
   arrays=[a for group in groups for a in group['arrays']]
   if {str(Path(d['path']).resolve()) for d in devices}!={str(Path(a['path']).resolve()) for a in arrays}:raise self.error('Hybrid layout does not match the mounted devices.',409)
   for a in arrays:self.read_array(a)
   for gi,group in enumerate(groups):
    for index,identifier in enumerate(group['disks']):
     affected=[a for a in group['arrays'] if index in a['layer']['members']]
     slots=[(a,a['layer']['members'].index(index)) for a in affected]
     online=all(self.array_slot(a,slot) is not None for a,slot in slots)
     disk=next((d for d in inventory if d['id']==identifier),{})
     minimum=max(a['layer']['end_mib'] for a in affected)*MIB+2*MIB
     members.append(dict(id=identifier,path=disk.get('path',''),label=disk.get('serial') or Path(identifier).name,size=disk.get('size',minimum),minimum=minimum,missing=not online,group=gi,index=index))
   mode=level
  elif str(info['source']).startswith('/dev/md') and level in ('1','5','6','10'):
   path=str(Path(info['source'].split('[')[0]).resolve());detail=self.run('mdadm','--detail','--export',path).stdout
   md_uuid=re.search(r'^MD_UUID=(\S+)$',detail,re.M)
   ids=config.get('disks',[])
   if not md_uuid or len(ids)<2:raise self.error('The saved RAID member identities are unavailable.',409)
   array=dict(path=path,uuid=md_uuid[1],members=ids,layer=dict(members=list(range(len(ids)))))
   md=self.read_array(array)
   if (md/'level').read_text().strip()!='raid'+level or int((md/'raid_disks').read_text())!=len(ids):raise self.error('The RAID geometry differs from the saved layout.',409)
   # Use a whole existing member's size, including the original data offset and
   # metadata reserve; component_size alone can underestimate the required disk.
   present=[d['size'] for d in inventory if d['id'] in ids]
   if not present:raise self.error('No physical RAID member can establish the replacement size.',409)
   minimum=min(present)
   for index,identifier in enumerate(ids):
    disk=next((d for d in inventory if d['id']==identifier),{})
    members.append(dict(id=identifier,path=disk.get('path',''),label=disk.get('serial') or Path(identifier).name,size=disk.get('size',minimum),minimum=minimum,missing=self.array_slot(array,index) is None,index=index))
   arrays=[array];mode='md-'+level
  elif not str(info['source']).startswith('/dev/md') and profiles.get('Data')=='RAID1' and profiles.get('Metadata') in ('RAID1','RAID1C3','RAID1C4') and profiles.get('System') in ('RAID1','RAID1C3','RAID1C4'):
   mode='native-raid1'
   recorded_sizes={}
   if any(d['size']==0 for d in devices):
    survivor=next((d['path'] for d in devices if d['path'].startswith('/dev/') and Path(d['path']).exists()),None)
    if not survivor:raise self.error('No surviving member is available.',409)
    tree=self.run('btrfs','inspect-internal','dump-tree','-t','chunk',survivor,timeout=30).stdout
    if 'fs uuid '+uuid not in tree:raise self.error('The surviving device identity differs from the mounted pool.',409)
    recorded_sizes={int(n):int(size) for n,size in re.findall(r'devid\s+(\d+)\s+total_bytes\s+(\d+)',tree)}
   for d in devices:
    if not d['size']:
     d['size']=recorded_sizes.get(d['devid'],0)
     if d['size']<=0:raise self.error('The missing member size could not be verified.',409)
    missing=d['path']=='missing' or not Path(d['path']).exists()
    if not missing:
     ancestry=self.run('lsblk','-s','-l','-n','-p','-o','TYPE,PATH',d['path']).stdout
     rows=[row.split() for row in ancestry.splitlines()]
     if any(row[0] not in ('disk','part') for row in rows if row):raise self.error('Only direct disk or partition mirrors support replacement.',409)
     parents=[row[1] for row in rows if len(row)==2 and row[0]=='disk']
     if len(parents)!=1:raise self.error('Physical member identity could not be verified.',409)
     tree=json.loads(self.run('lsblk','-J','--tree','-p','-o','PATH,TYPE,MOUNTPOINTS',parents[0]).stdout)['blockdevices']
     def other_mount(node):
      return any(p and p!=mount and not p.startswith(mount+'/') for p in node.get('mountpoints') or []) or any(other_mount(child) for child in node.get('children',[]))
     if any(other_mount(node) for node in tree):raise self.error('A pool member shares its physical disk with another mounted filesystem. Automatic retirement is disabled.',409)
     disk=next((item for item in inventory if item['path']==parents[0]),{})
    else:disk={}
    cached=config.get('native_members',{}).get(str(d['devid']),{}) if missing else {}
    members.append(dict(id=str(d['devid']),path=d['path'],disk_id=disk.get('id',cached.get('disk_id','')),label=disk.get('serial') or cached.get('label') or ('Missing device '+str(d['devid']) if missing else d['path']),size=d['size'],minimum=d['size'],missing=missing))
   # Some btrfs-progs omit the missing row. Never silently hide it.
   total=re.search(r'Total devices\s+(\d+)',show)
   if not total or len(members)!=int(total[1]):raise self.error('A missing member cannot be identified. Mount the pool degraded and inspect device IDs before repair.',409)
  else:raise self.error('Drive replacement requires a redundant native mirror, MD RAID1/5/6/10, or Harbour Hybrid1/2 pool. Missing data on RAID0, JBOD and Basic cannot be reconstructed.',409)
  return dict(uuid=uuid,mode=mode,name=config.get('name','Data volume'),members=members,profiles=profiles,arrays=arrays,free=info['free'],total=info['total'],used=int(re.search(r'^\s*Used:\s+(\d+)',usage,re.M)[1]))

 def read_array(self,array):
  detail=self.run('mdadm','--detail','--export',array['path']).stdout
  if 'MD_UUID='+array['uuid'] not in detail.splitlines():raise self.error('A RAID tier UUID changed. No disk changes are allowed.',409)
  md=Path('/sys/class/block')/Path(array['path']).resolve().name/'md'
  if not md.is_dir() or (md/'array_state').read_text().strip() in ('inactive','clear'):raise self.error('A RAID tier is inactive. Assemble it before repair.',409)
  return md

 def array_slot(self,array,slot):
  md=self.read_array(array)
  for entry in md.glob('dev-*'):
   states=set((entry/'state').read_text().strip().split(','))
   if (entry/'slot').read_text().strip()==str(slot) and 'in_sync' in states and not states.intersection(('faulty','blocked','write_error')):
    return str((entry/'block').resolve())
  return None

 def lifecycle_info(self):
  try:
   state=self.lifecycle_state();state.pop('arrays',None)
   inventory={d['id']:d for d in self.inventory()}
   for member in state['members']:
    disk=inventory.get(member.get('disk_id'),{})
    member.update(health=disk.get('health','unknown'),health_reasons=disk.get('health_reasons',[]))
   return dict(state,supported=True,pending=self.pending().exists())
  except Exception as error:return dict(supported=False,reason=str(error),members=[])

 def lifecycle_checkpoint(self):
  state=self.lifecycle_state();config=self.app.config.setdefault('storage',{});config['uuid']=state['uuid']
  if state['mode']=='native-raid1':
   config['native_members']={m['id']:m for m in state['members']}
   config['disks']=list(dict.fromkeys(m['disk_id'] for m in state['members'] if m['disk_id']))
  self.app.save();return self.lifecycle_info()

 def lifecycle_validate(self,state,member,operation):
  if operation not in ('replace','remove'):raise self.error('Choose replace or remove.')
  missing=[m for m in state['members'] if m['missing']]
  if state['mode']=='native-raid1':
   if len(missing)>1:raise self.error('More than one mirror member is missing. Automatic repair is unsafe.',409)
   exclusive=Path('/sys/fs/btrfs')/state['uuid']/'exclusive_operation'
   if exclusive.exists() and exclusive.read_text().strip()!='none':raise self.error('Wait for the current filesystem operation to finish.',409)
   if operation=='remove':
    copies=max({'RAID1':2,'RAID1C3':3,'RAID1C4':4}.get(p,2) for p in state['profiles'].values())
    remaining=[m['size'] for m in state['members'] if m['id']!=member['id']]
    if missing or len(remaining)<copies:raise self.error('Removing this disk would reduce protection. Connect a spare and use Replace drive instead.',409)
    used=state['used'];capacity=mirror_capacity(remaining)
    if capacity<used+max(256*MIB,used//5):raise self.error('The remaining disks need more free working space to evacuate this member.',409)
  else:
   group={'arrays':state['arrays']} if state['mode'].startswith('md-') else self.app.config['storage']['hybrid']['groups'][member['group']]
   for array in group['arrays']:
    if member['index'] not in array['layer']['members']:continue
    md=self.read_array(array)
    if (md/'sync_action').read_text().strip()!='idle':raise self.error('Wait for RAID synchronization to finish before another disk change.',409)
    absent=[slot for slot in range(len(array['members'])) if self.array_slot(array,slot) is None]
    slot=array['layer']['members'].index(member['index'])
    if operation=='remove' and absent:raise self.error('Every affected tier must be healthy before retiring a disk.',409)
    if operation=='replace' and absent and (not member['missing'] or slot!=min(absent)):raise self.error('Repair the first missing disk in this protected group before this member.',409)
   if operation=='remove' and member['missing']:raise self.error('This disk is already detached. Use Repair pool.',409)

 def lifecycle_plan(self,data):
  self.check_pending();state=self.lifecycle_state()
  member=next((m for m in state['members'] if m['id']==data.get('member')),None)
  if not member:raise self.error('Choose a current pool member.',409)
  operation=data.get('operation');self.lifecycle_validate(state,member,operation)
  target=None;unknown=[]
  if operation=='replace':
   disks,_=self.selection([data.get('target')],'basic');target=disks[0]
   logical={m.get('disk_id',m['id']) for m in state['members']}|set(self.app.config.get('storage',{}).get('disks',[]))
   if target['id'] in logical:raise self.error('The replacement is already recorded as a pool member.',409)
   if target['size']<member['minimum']:raise self.error('The replacement disk is too small for this member.',409)
   unknown=self.health(disks)
  from storage import identity
  token=secrets.token_urlsafe(24);confirmation=('REPLACE ' if operation=='replace' else 'REMOVE ')+member['label']
  self.plans={key:value for key,value in self.plans.items() if value['expires']>time.monotonic()}
  if len(self.plans)>=20:raise self.error('Too many storage plans. Wait five minutes.',409)
  plan=dict(kind='member',expires=time.monotonic()+300,uuid=state['uuid'],mode=state['mode'],member=member,operation=operation,target=target,target_identity=identity(target) if target else None,confirmation=confirmation)
  if state['mode'] in HYBRID_LEVELS:plan['old_arrays']=copy.deepcopy(self.app.config['storage']['hybrid']['groups'][member['group']]['arrays'])
  elif state['mode'].startswith('md-'):plan['old_arrays']=copy.deepcopy(state['arrays'])
  self.plans[token]=plan
  warning=('Only the replacement disk will be erased. Keep the old disk connected until completion.' if target else 'Files will be evacuated before this disk is released.' if state['mode']=='native-raid1' else 'This disk will be detached from every tier. Protection is reduced until you install a replacement and repair the pool. This does not shrink the pool.')
  return dict(token=token,member=member,target=target,confirmation=confirmation,warning=warning,health_unknown=unknown,health_warnings=getattr(unknown,'warnings',[]))

 def lifecycle_action(self,data):
  with self.app.lock:
   plan=self.plans.get(data.get('token',''))
   if not plan or plan.get('kind')!='member' or plan['expires']<time.monotonic():raise self.error('The disk plan expired. Review it again.',409)
   if data.get('acknowledge') is not True or data.get('confirmation')!=plan['confirmation']:raise self.error('Confirm the exact disk action.',409)
   plan=self.plans.pop(data['token'])
  def execute():
   self.check_pending();state=self.lifecycle_state()
   if (state['uuid'],state['mode'])!=(plan['uuid'],plan['mode']):raise self.error('The pool changed. No disks were modified.',409)
   member=next((m for m in state['members'] if m==plan['member']),None)
   if not member:raise self.error('The pool member changed. Review the disk again.',409)
   self.lifecycle_validate(state,member,plan['operation'])
   target=plan['target'];old_parts=[]
   if target:
    from storage import identity
    disks,_=self.selection([target['id']],'basic')
    if identity(disks[0])!=plan['target_identity']:raise self.error('Replacement identity changed.',409)
    self.health(disks);old_parts=self.array_preflight(disks)
    # Revalidate after slow SMART/preflight calls, immediately before writing.
    fresh=self.lifecycle_state()
    if fresh['uuid']!=state['uuid'] or fresh['members']!=state['members']:raise self.error('Pool membership changed. No disks were modified.',409)
    self.lifecycle_validate(fresh,member,plan['operation'])
    disks,_=self.selection([target['id']],'basic')
    if identity(disks[0])!=plan['target_identity']:raise self.error('Replacement identity changed.',409)
   self.record(dict(kind='member',stage='started',plan=plan))
   if state['mode']=='native-raid1':self.native_member(plan,old_parts)
   else:self.hybrid_member(plan,old_parts)
   self.pending().unlink();return {'message':'Replacement complete. The old disk can now be removed.' if target else 'Disk released. Shut down before physically removing a disk unless your hardware supports hot swap.'}
  return self.app.job('Replace drive' if plan['target'] else 'Remove drive',execute,kind='storage')

 def monitored(self,args,status):
  with ThreadPoolExecutor(max_workers=1) as executor:
   future=executor.submit(self.run,*args,timeout=86400)
   while not future.done():
    try:self.app.job_progress('Copying / rebuilding data',status())
    except Exception:pass
    time.sleep(2)
   return future.result()

 def native_member(self,plan,old_parts,resume=False):
  mount=str(self.app.storage);member=plan['member'];target=plan['target']
  if target:
   if resume:
    show=self.run('btrfs','filesystem','show','--raw',mount).stdout
    current=next((p for n,p in re.findall(r'devid\s+(\d+).*?\bpath\s+(\S+)',show) if n==member['id']),None)
    if current and Path(current).resolve()==Path(target['id']).resolve():
     self.finish_native(plan);return
    status=self.run('btrfs','replace','status','-1',mount).stdout
    if 'finished on' not in status and re.search(r'\d+\.\d+%',status):
     deadline=time.monotonic()+86400
     while time.monotonic()<deadline:
      status=self.run('btrfs','replace','status','-1',mount).stdout
      self.app.job_progress('Resuming mirror replacement',status.strip())
      if 'finished on' in status:break
      if 'canceled' in status.lower():raise self.error('The kernel canceled the replacement. Manual review is required.',409)
      time.sleep(2)
     show=self.run('btrfs','filesystem','show','--raw',mount).stdout
     current=next((p for n,p in re.findall(r'devid\s+(\d+).*?\bpath\s+(\S+)',show) if n==member['id']),None)
     if current and Path(current).resolve()==Path(target['id']).resolve():self.finish_native(plan);return
     raise self.error('Replacement is not complete. Keep both disks connected.',409)
    # A target already in use is never erased while attempting a restart.
    self.selection([target['id']],'basic')
   for part in old_parts:self.run('wipefs','--all',part,timeout=30)
   self.run('wipefs','--all',target['id'],timeout=30)
   self.record(dict(kind='member',stage='prepared',plan=plan))
   self.monitored(('btrfs','replace','start','-B','-r',member['id'],target['id'],mount),lambda:self.run('btrfs','replace','status','-1',mount).stdout.strip())
   status=self.run('btrfs','replace','status','-1',mount).stdout
   if 'finished on' not in status or '0 write errs, 0 uncorr. read errs' not in status:raise self.error('Replacement reported errors. Keep the old disk and review the recovery journal.',409)
   show=self.run('btrfs','filesystem','show','--raw',mount).stdout
   path=next((p for n,p in re.findall(r'devid\s+(\d+).*?\bpath\s+(\S+)',show) if n==member['id']),None)
   if not path or Path(path).resolve()!=Path(target['id']).resolve():raise self.error('Replacement completion could not be verified. Retain the recovery journal.',409)
  else:
   if resume and member['id'] not in [m['id'] for m in self.lifecycle_state()['members']]:self.finish_native(plan);return
   self.monitored(('btrfs','device','remove',member['id'],mount),lambda:'Evacuating data. The disk stays connected until completion.')
  self.finish_native(plan)

 def finish_native(self,plan):
  member=plan['member'];target=plan['target']
  config=self.app.config.setdefault('storage',{});config['uuid']=plan['uuid']
  disks=config.get('disks',[]);old=member.get('disk_id')
  # Keep unrelated entries and remove only the selected physical member.
  config['disks']=[(target['id'] if target else None) if d==old else d for d in disks]
  config['disks']=[d for d in config['disks'] if d]
  if target and target['id'] not in config['disks']:config['disks'].append(target['id'])
  self.app.save()
  self.lifecycle_checkpoint()

 def hybrid_member(self,plan,old_parts,resume=False):
  member=plan['member'];target=plan['target'];raw=plan['mode'].startswith('md-')
  group={'arrays':plan['old_arrays']} if raw else self.app.config['storage']['hybrid']['groups'][member['group']]
  arrays=plan.get('old_arrays',group['arrays'])
  affected=[(i,a,a['layer']['members'].index(member['index'])) for i,a in enumerate(arrays) if member['index'] in a['layer']['members']]
  if target and not resume:
   for part in old_parts:self.run('wipefs','--all',part,timeout=30)
   self.run('wipefs','--all',target['id'],timeout=30)
   if not raw:
    self.run('parted','--script',target['id'],'mklabel','gpt',timeout=30)
    for i,array,slot in affected:
     layer=array['layer'];self.run('parted','--script',target['id'],'mkpart','primary',str(layer['start_mib'])+'MiB',str(layer['end_mib'])+'MiB',timeout=30)
     self.run('parted','--script',target['id'],'set',str(i+1),'raid','on',timeout=30)
   self.run('udevadm','settle',timeout=30)
   self.record(dict(kind='member',stage='prepared',plan=plan))
  for i,array,slot in affected:
   old=array['members'][slot]
   if not target:
    if self.array_slot(array,slot) is not None:
     self.run('mdadm',array['path'],'--fail',old);self.run('mdadm',array['path'],'--remove',old)
    continue
   new=target['id'] if raw else target['id']+'-part'+str(i+1)
   if not Path(new).is_block_device():raise self.error('Replacement partition identity did not appear.',409)
   md=self.read_array(array);entry=md/('dev-'+Path(new).resolve().name)
   if not entry.exists():
    absent=[n for n in range(len(array['members'])) if self.array_slot(array,n) is None]
    if absent and slot!=min(absent):raise self.error('Another lower RAID slot is missing. Repair it first before resuming this disk.',409)
    if any((Path('/sys/class/block')/Path(new).resolve().name/'holders').glob('*')):raise self.error('The replacement partition is held by different active storage.',409)
    if not resume:self.run('wipefs','--all',new,timeout=30)
    self.run('mdadm',array['path'],'--add',new)
   current=self.array_slot(array,slot)
   if current and Path(current).name==Path(old).resolve().name:self.run('mdadm',array['path'],'--replace',old,'--with',new)
   self.app.job_progress('Rebuilding protected tier','Tier '+str(i+1)+'. Keep all disks connected.')
   deadline=time.monotonic()+86400
   idle_since=None
   while True:
    md=self.read_array(array);action=(md/'sync_action').read_text().strip();done=(md/'sync_completed').read_text().strip()
    block=self.array_slot(array,slot)
    if block and Path(block).name==Path(new).resolve().name and action=='idle':break
    if action=='idle':
     idle_since=idle_since or time.monotonic()
     if time.monotonic()-idle_since>15:raise self.error('RAID stopped rebuilding before the expected replacement became active. Review the recovery journal.',409)
    else:idle_since=None
    if time.monotonic()>deadline:raise self.error('Rebuild is still running. Keep the recovery journal and disks connected.',409)
    self.app.job_progress('Rebuilding protected tier','Tier '+str(i+1)+' · '+action+' · '+done);time.sleep(2)
   if (md/('dev-'+Path(old).resolve().name)).exists():
    # A completed copy-first replacement leaves the old device faulty/spare.
    self.run('mdadm',array['path'],'--remove',old)
  if target:
   updated=copy.deepcopy(self.app.config['storage'])
   if not raw:
    g=updated['hybrid']['groups'][member['group']]
    for i,array,slot in affected:g['arrays'][i]['members'][slot]=target['id']+'-part'+str(i+1)
    g['disks'][member['index']]=target['id']
   updated['disks']=[target['id'] if d==member['id'] else d for d in updated['disks']]
   self.app.config['storage']=updated;self.app.save();self.save_arrays()

 def lifecycle_resume(self,data):
  if data.get('confirmation')!='RESUME REPAIR' or data.get('acknowledge') is not True:raise self.error('Confirm resuming the recorded disk operation.',409)
  if not self.recovery_pending():raise self.error('No interrupted storage operation is available to resume.',409)
  journal=json.loads(self.pending().read_text());plan=journal.get('plan',{})
  if journal.get('kind')!='member' or plan.get('kind')!='member':raise self.error('This recovery journal requires manual review.',409)
  state=self.lifecycle_state()
  if (state['uuid'],state['mode'])!=(plan['uuid'],plan['mode']):raise self.error('The pool identity changed. Recovery is blocked.',409)
  target=plan.get('target')
  if target:
   actual=next((d for d in self.inventory() if d['id']==target['id']),None)
   if not actual or any(actual[k]!=target[k] for k in ('id','size','serial','wwn')):raise self.error('The recorded replacement disk is absent or changed.',409)
  def execute():
   self.app.job_progress('Resuming recorded disk operation','The recorded replacement is retained. Integrated devices are never reformatted.')
   if state['mode']=='native-raid1':self.native_member(plan,[],resume=True)
   elif journal.get('stage')=='prepared' or not target:self.hybrid_member(plan,[],resume=True)
   else:raise self.error('Disk preparation was interrupted. Manual partition inspection is required before resuming.',409)
   self.pending().unlink();return {'message':'Disk operation completed.'}
  return self.app.job('Resume drive repair',execute,kind='storage')
