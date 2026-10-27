"""Guarded hybrid creation and protected online expansion."""
import json,os,re,secrets,shutil,time
from pathlib import Path
from hybrid_layout import HYBRID_LEVELS,layout,mirror_capacity,MIB

def atomic_text(path,text):
 temporary=path.with_name(path.name+'.harbour-new')
 fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as stream:
  stream.write(text);stream.flush();os.fsync(stream.fileno())
 os.replace(temporary,path)
 directory=os.open(path.parent,os.O_RDONLY)
 try:os.fsync(directory)
 finally:os.close(directory)

class HybridStorage:
 def hybrid_status(self):
  config=self.app.config.get('storage',{})
  if config.get('level') not in HYBRID_LEVELS:return None
  arrays=[]
  for group in config.get('hybrid',{}).get('groups',[]):
   for record in group['arrays']:
    md=Path('/sys/class/block')/Path(record['path']).resolve().name/'md'
    item={'path':record['path']}
    try:
     for field in ('level','array_state','degraded','sync_action','sync_completed'):item[field]=(md/field).read_text().strip()
     item['healthy']=item['degraded']=='0' and item['array_state'] not in ('inactive','clear')
    except OSError:item.update(healthy=False,array_state='missing')
    arrays.append(item)
  return {'name':HYBRID_LEVELS[config['level']]['name'],'arrays':arrays,'healthy':bool(arrays) and all(a['healthy'] for a in arrays)}
 def pending(self):
  return self.app.state/'storage-operation.json'
 def recovery_pending(self):
  if not self.pending().exists():return False
  with self.app.lock:
   active=any(job.get('kind')=='storage' and job.get('state') in ('queued','running') for job in getattr(self.app,'jobs',{}).values())
  return not active
 def record(self,value):
  atomic_text(self.pending(),json.dumps(value,indent=2)+'\n')
 def check_pending(self):
  if self.pending().exists():raise self.error('A storage operation needs recovery. Review storage-operation.json before making further disk changes.',409)
 def hybrid_arrays(self,level,disks,group):
  result=layout(level,[d['size'] for d in disks]);prefix='harbour-h'+str(result['protection'])+'-g'+str(group)
  arrays=[{'path':'/dev/md/'+prefix+'-t'+str(i),'name':prefix+'-t'+str(i),'layer':layer} for i,layer in enumerate(result['layers'])]
  if any(Path(a['path']).exists() for a in arrays):raise self.error('A hybrid array name is already in use. No disks were modified.',409)
  return result,arrays
 def array_preflight(self,disks):
  missing=[name for name in ('wipefs','parted','mdadm','mkfs.btrfs','blkid','udevadm','systemctl','systemd-run','update-initramfs') if not shutil.which(name)]
  if missing:raise self.error('Required storage tools are missing: '+', '.join(missing)+'. No disks were modified.',409)
  self.app.job_progress('Checking unused partitions','Inspecting existing signatures, active holders and mounted filesystems before any disk write.')
  old_partitions=[]
  for disk in disks:
   tree=json.loads(self.run('lsblk','-J','--tree','-p','-o','PATH,TYPE,MOUNTPOINTS',disk['id']).stdout)['blockdevices']
   def inspect(node):
    if node.get('type') not in ('disk','part') or any(node.get('mountpoints') or []):raise self.error('A selected disk acquired active storage. No disks were modified.',409)
    if node['type']=='part':old_partitions.append(node['path'])
    for child in node.get('children',[]):inspect(child)
   if len(tree)!=1 or Path(tree[0]['path']).resolve()!=Path(disk['path']).resolve():raise self.error('Disk path identity changed. No disks were modified.',409)
   inspect(tree[0])
  return old_partitions
 def make_arrays(self,disks,arrays,old_partitions):
  # Old partition MD signatures must be removed before recreating their offsets,
  # otherwise udev can automatically reassemble an old array during partitioning.
  for partition in old_partitions:self.run('wipefs','--all',partition,timeout=30)
  for disk in disks:
   self.run('wipefs','--all',disk['id'],timeout=30)
   self.run('parted','--script',disk['id'],'mklabel','gpt',timeout=30)
  for i,array in enumerate(arrays):
   layer=array['layer'];members=[]
   for index in layer['members']:
    disk=disks[index];part=i+1
    self.run('parted','--script','--align','optimal',disk['id'],'mkpart','primary',str(layer['start_mib'])+'MiB',str(layer['end_mib'])+'MiB',timeout=30)
    self.run('parted','--script',disk['id'],'set',str(part),'raid','on',timeout=30)
    members.append(disk['id']+'-part'+str(part))
   self.run('udevadm','settle',timeout=30)
   if any(not Path(p).is_block_device() for p in members):raise self.error('A stable partition identifier did not appear. Storage operation retained for recovery.',409)
   for member in members:self.run('wipefs','--all',member,timeout=30)
   self.app.job_progress('Creating protected group','Creating RAID '+layer['raid']+' tier '+str(i+1)+'. Initial synchronization continues in the background.')
   self.run('mdadm','--create',array['path'],'--metadata=1.2','--name='+array['name'],'--level='+layer['raid'],
    '--raid-devices='+str(len(members)),'--data-offset=4M','--size='+str(layer['component_kib']),'--run',*members,timeout=120)
   self.run('udevadm','settle',timeout=30)
   array['uuid']=self.run('mdadm','--detail','--export',array['path']).stdout
   match=re.search(r'^MD_UUID=(\S+)$',array['uuid'],re.M)
   if not match:raise self.error('The new RAID identity could not be verified.',409)
   array['uuid']=match[1];array['members']=members
  return arrays
 def save_arrays(self):
  self.app.job_progress('Saving RAID boot configuration','Recording arrays and rebuilding the boot image before integrating new capacity.')
  conf=Path('/etc/mdadm/mdadm.conf');scan=self.run('mdadm','--detail','--scan').stdout
  existing=conf.read_text();uuids=set(re.findall(r'UUID=(\S+)',existing))
  additions=[]
  for line in scan.splitlines():
   match=re.search(r'UUID=(\S+)',line)
   if match and match[1] not in uuids:additions.append(line);uuids.add(match[1])
  atomic_text(conf,existing+'\n'+'\n'.join(additions)+'\n')
  self.run('systemd-run','--wait','--pipe','--collect','--unit=harbor-storage-initramfs','/usr/sbin/update-initramfs','-u',timeout=600)
 def checked_disks(self,plan):
  disks,_=self.selection(plan['ids'],plan['selection_level'])
  from storage import identity
  if [identity(d) for d in disks]!=plan['identities']:raise self.error('Disk identities changed. No disks were modified.',409)
  self.health(disks)
  current,_=self.selection(plan['ids'],plan['selection_level'])
  if [identity(d) for d in current]!=plan['identities']:raise self.error('Disk identities changed. No disks were modified.',409)
  return current
 def create_hybrid(self,plan):
  def execute():
   self.assert_empty();self.check_pending()
   plan['selection_level']=plan['level'];disks=self.checked_disks(plan)
   result,arrays=self.hybrid_arrays(plan['level'],disks,0)
   disks=self.checked_disks(plan)  # Immediately before the first write.
   old_partitions=self.array_preflight(disks)
   self.record({'kind':'hybrid-create','plan':plan,'arrays':arrays})
   self.make_arrays(disks,arrays,old_partitions);self.record({'kind':'hybrid-create','stage':'arrays-created','plan':plan,'arrays':arrays});self.save_arrays()
   self.app.job_progress('Creating filesystem','Formatting Btrfs over the protected RAID tiers.')
   self.run('mkfs.btrfs','-f','-L','harbor-data','-d','single','-m','dup',*[a['path'] for a in arrays],timeout=300)
   uuid=self.run('blkid','-s','UUID','-o','value',arrays[0]['path']).stdout.strip()
   if not re.fullmatch(r'[a-fA-F0-9-]{36}',uuid):raise self.error('The filesystem UUID could not be verified.',409)
   fstab=Path('/etc/fstab');lines=[l for l in fstab.read_text().splitlines() if len(l.split())<2 or l.split()[1]!=str(self.app.storage)]
   lines.append(f'UUID={uuid} {self.app.storage} btrfs defaults,nofail,x-systemd.device-timeout=30 0 0');atomic_text(fstab,'\n'.join(lines)+'\n')
   self.run('systemctl','daemon-reload')
   unit=self.run('systemd-escape','--path','--suffix=mount',str(self.app.storage)).stdout.strip()
   if not re.fullmatch(r'[A-Za-z0-9_.\\-]+\.mount',unit):raise self.error('Invalid storage mount unit.',409)
   self.run('systemctl','start',unit,timeout=120)
   if not self.app.storage_info()['mounted']:raise self.error('The hybrid filesystem did not become visible.',409)
   (self.app.storage/'shares').mkdir(exist_ok=True);(self.app.storage/'shares').chmod(0o755)
   self.app.config['storage']={'name':plan['name'],'level':plan['level'],'uuid':uuid,'disks':plan['ids'],
    'hybrid':{'format':1,'groups':[{'arrays':arrays,'layout':result,'disks':plan['ids']}], 'expansion':'protected-groups'}}
   self.app.save();self.app.sync_samba();self.pending().unlink()
   return self.app.storage_info()
  return self.app.job('Create '+HYBRID_LEVELS[plan['level']]['name']+' storage',execute,kind='storage',target=plan['name'])
 def pool_state(self):
  if self.app.demo:raise self.error('Storage expansion is available on an installed appliance.',409)
  info=self.app.storage_info()
  if not info['mounted'] or info.get('filesystem')!='btrfs':raise self.error('A mounted Btrfs data pool is required.',409)
  if info.get('healthy') is False:raise self.error('Repair the pool before expanding it.',409)
  show=self.run('btrfs','filesystem','show','--raw',str(self.app.storage)).stdout
  if re.search('missing',show,re.I):raise self.error('A pool device is missing. Repair it before expansion.',409)
  match=re.search(r'uuid:\s*([a-fA-F0-9-]{36})',show)
  if not match:raise self.error('Could not verify the current pool UUID.',409)
  self.run('btrfs','device','stats','-c',str(self.app.storage),timeout=20)
  balance=self.run('btrfs','balance','status',str(self.app.storage),check=False)
  if 'No balance found' not in balance.stdout:raise self.error('Finish or cancel the current filesystem balance before expansion.',409)
  usage=self.run('btrfs','filesystem','usage','-b',str(self.app.storage)).stdout
  profiles=dict(re.findall(r'^(Data|Metadata|System),([^:]+):',usage,re.M))
  storage=self.app.config.get('storage',{});level=storage.get('level')
  if level in HYBRID_LEVELS:
   hybrid=storage.get('hybrid',{})
   if hybrid.get('format')!=1 or not hybrid.get('groups'):raise self.error('Hybrid layout metadata is missing; automatic expansion is disabled.',409)
   if profiles.get('Data')!='single' or profiles.get('Metadata')!='DUP':raise self.error('Hybrid filesystem profiles changed. Review the pool manually.',409)
   actual={str(Path(p).resolve()) for p in re.findall(r'\bpath\s+(/dev/\S+)',show)}
   recorded={str(Path(a['path']).resolve()) for g in hybrid['groups'] for a in g['arrays']}
   if actual!=recorded:raise self.error('The filesystem devices do not match the saved hybrid layout. Review the pool before expansion.',409)
   for group in hybrid['groups']:
    for array in group['arrays']:
     detail=self.run('mdadm','--detail','--export',array['path']).stdout
     if 'MD_UUID='+array['uuid'] not in detail.splitlines():raise self.error('A RAID tier identity changed. Review the pool before expansion.',409)
     md=Path('/sys/class/block')/Path(array['path']).resolve().name/'md'
     if not md.is_dir() or (md/'degraded').read_text().strip()!='0' or (md/'sync_action').read_text().strip()!='idle':raise self.error('Wait for every RAID tier to become healthy and finish synchronization.',409)
   mode=level;minimum=HYBRID_LEVELS[level]['minimum']
  elif not str(info['source']).startswith('/dev/md') and profiles.get('Data')=='RAID1' and profiles.get('Metadata') in ('RAID1','RAID1C3','RAID1C4'):
   mode='native-raid1';minimum=1
  else:raise self.error('Expansion currently supports Harbour Hybrid pools and native Btrfs RAID1 pools.',409)
  if mode=='native-raid1':
   parents=[]
   for device in re.findall(r'\bpath\s+(/dev/\S+)',show):
    ancestry=self.run('lsblk','-s','-l','-n','-p','-o','TYPE,PATH',device).stdout
    rows=[line.split() for line in ancestry.splitlines()]
    if any(row[0] not in ('disk','part') for row in rows if row):raise self.error('Native RAID1 expansion requires direct disk or partition members.',409)
    disks=[row[1] for row in rows if len(row)==2 and row[0]=='disk']
    if len(disks)!=1 or disks[0] in parents:raise self.error('Native RAID1 members must reside on distinct physical disks.',409)
    parents.extend(disks)
   if len(parents)<2:raise self.error('Could not verify the physical RAID1 members.',409)
  sizes=[int(v) for v in re.findall(r'devid\s+\d+\s+size\s+(\d+)',show)]
  return {'uuid':match[1],'mode':mode,'minimum':minimum,'name':storage.get('name','Data volume'),'sizes':sizes,'free':info['free'],'total':info['total']}
 def expansion_info(self):
  try:
   self.check_pending();state=self.pool_state()
   return dict(state,supported=True,description=('Add at least '+str(state['minimum'])+' unused disks as a new protected group. Existing tiers are retained.' if state['mode']!='native-raid1' else 'Add unused disks while retaining the current Btrfs RAID1 profiles. Existing pool data is retained.'))
  except Exception as error:return {'supported':False,'reason':str(error)}
 def expand_plan(self,data):
  self.check_pending();state=self.pool_state();ids=data.get('disks')
  level=state['mode'] if state['mode'] in HYBRID_LEVELS else ('basic' if isinstance(ids,list) and len(ids)==1 else 'linear')
  disks,_=self.selection(ids,level)
  if any(d['size']<512*MIB for d in disks):raise self.error('New data disks must be at least 512 MiB.',409)
  unknown=self.health(disks)
  existing=len(self.app.config.get('storage',{}).get('disks',[])) if state['mode'] in HYBRID_LEVELS else len(state['sizes'])
  if existing+len(disks)>24:raise self.error('This release supports at most 24 disks per pool.',409)
  result=layout(level,[d['size'] for d in disks]) if level in HYBRID_LEVELS else None
  if state['mode']=='native-raid1' and state['free']<max(64*MIB,min(1024*MIB,state['total']//10)):raise self.error('Free working space is required for the RAID1 balance before expansion.',409)
  gain=result['capacity'] if result else mirror_capacity(state['sizes']+[d['size'] for d in disks])-mirror_capacity(state['sizes'])
  from storage import identity
  token=secrets.token_urlsafe(24)
  self.plans={k:v for k,v in self.plans.items() if v['expires']>time.monotonic()}
  if len(self.plans)>=20:raise self.error('Too many outstanding storage plans.',409)
  self.plans[token]={'kind':'expand','expires':time.monotonic()+300,'name':state['name'],'selection_level':level,'mode':state['mode'],
   'uuid':state['uuid'],'ids':[d['id'] for d in disks],'identities':[identity(d) for d in disks]}
  return {'token':token,'name':state['name'],'mode':state['mode'],'disks':disks,'capacity_gain':gain,'layout':result,'health_unknown':unknown,'health_warnings':getattr(unknown,'warnings',[]),
   'confirmation':'EXPAND '+state['name'],'warning':'Only the selected NEW disks will be erased. Existing pool data is retained. Keep an independent backup.'}
 def expand(self,data):
  with self.app.lock:
   plan=self.plans.get(data.get('token',''))
   if not plan or plan.get('kind')!='expand' or plan['expires']<time.monotonic():raise self.error('The expansion plan expired. Review the disks again.',409)
   if data.get('acknowledge') is not True or data.get('confirmation')!='EXPAND '+plan['name']:raise self.error('Confirm expansion using the exact pool name.',409)
   plan=self.plans.pop(data['token'])
  def execute():
   self.check_pending();state=self.pool_state()
   if state['uuid']!=plan['uuid'] or state['mode']!=plan['mode']:raise self.error('The pool changed. No disks were modified.',409)
   disks=self.checked_disks(plan);arrays=[];result=None
   if plan['mode'] in HYBRID_LEVELS:
    result,arrays=self.hybrid_arrays(plan['mode'],disks,len(self.app.config['storage']['hybrid']['groups']))
   disks=self.checked_disks(plan)
   final=self.pool_state()
   if final['uuid']!=plan['uuid'] or final['mode']!=plan['mode']:raise self.error('The pool changed. No disks were modified.',409)
   old_partitions=self.array_preflight(disks) if arrays else []
   self.record({'kind':'expand','plan':plan,'arrays':arrays})
   if arrays:
    self.make_arrays(disks,arrays,old_partitions);self.record({'kind':'expand','stage':'arrays-created','plan':plan,'arrays':arrays});self.save_arrays();devices=[a['path'] for a in arrays]
   else:
    if not shutil.which('wipefs'):raise self.error('wipefs is unavailable. No disks were modified.',409)
    for disk in disks:self.run('wipefs','--all',disk['id'],timeout=30)
    devices=plan['ids']
   self.app.job_progress('Adding protected capacity','Adding new devices without formatting the existing filesystem.')
   self.run('btrfs','device','add',*devices,str(self.app.storage),timeout=180)
   storage=self.app.config.setdefault('storage',{});storage.setdefault('disks',[]).extend(plan['ids'])
   if arrays:storage['hybrid']['groups'].append({'arrays':arrays,'layout':result,'disks':plan['ids']})
   storage['uuid']=plan['uuid'];self.app.save()
   if not arrays:
    self.app.job_progress('Redistributing mirrored data','Balancing the existing RAID1 profiles across the expanded pool. This may take a long time.')
    self.run('btrfs','balance','start',str(self.app.storage),timeout=86400)
   self.pending().unlink();return self.app.storage_info()
  return self.app.job('Expand '+plan['name'],execute,kind='storage',target=plan['name'])
