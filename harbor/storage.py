"""Storage creation with stable disk identities, preflight plans and revalidation."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
from hybrid_layout import HYBRID_LEVELS, layout
from hybrid_storage import HybridStorage
from drive_lifecycle import DriveLifecycle

LEVELS = {
    'basic': {'name':'Basic','minimum':1,'maximum':1,'description':'One disk. No drive-failure protection.'},
    'linear': {'name':'JBOD','minimum':2,'maximum':24,'description':'Combine capacity. No drive-failure protection.'},
    '0': {'name':'RAID 0','minimum':2,'maximum':24,'description':'Maximum speed and capacity. No drive-failure protection.'},
    '1': {'name':'RAID 1','minimum':2,'maximum':2,'description':'Mirrored disks. Survives one drive failure.'},
    '5': {'name':'RAID 5','minimum':3,'maximum':24,'description':'Balanced capacity. Survives one drive failure.'},
    '6': {'name':'RAID 6','minimum':4,'maximum':24,'description':'Double parity. Survives two drive failures.'},
    '10': {'name':'RAID 10','minimum':4,'maximum':24,'description':'Striped mirrors. Requires an even number of disks.'},
}
LEVELS.update(HYBRID_LEVELS)


def capacity(level, sizes):
    if level not in LEVELS:
        raise ValueError('Choose a supported RAID level.')
    rules=LEVELS[level]
    if not rules['minimum'] <= len(sizes) <= rules['maximum'] or (level=='10' and len(sizes)%2):
        raise ValueError('The selected disk count does not fit this RAID level.')
    if level in HYBRID_LEVELS:return layout(level,sizes)['capacity']
    smallest=min(sizes)
    return {'basic':smallest,'linear':sum(sizes),'0':smallest*len(sizes),'1':smallest,
            '5':smallest*(len(sizes)-1),'6':smallest*(len(sizes)-2),'10':smallest*(len(sizes)//2)}[level]


def descendants(disk):
    yield disk
    for child in disk.get('children',[]):
        yield from descendants(child)


def identity(disk):
    return hashlib.sha256(json.dumps({k:disk.get(k) for k in ('path','size','serial','wwn','id')},sort_keys=True).encode()).hexdigest()


class StorageManager(HybridStorage,DriveLifecycle):
    def __init__(self, app, run, error):
        self.app,self.run,self.error=app,run,error
        self.plans={}

    def inventory(self):
        if self.app.demo:
            return []
        tree=json.loads(self.run('lsblk','-J','-b','-p','-o','NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL,WWN,RO,RM').stdout)['blockdevices']
        # lsblk reports the mount only on one Btrfs member. Protect every member.
        btrfs=self.run('btrfs','filesystem','show','--mounted','--raw',check=False)
        uncertain_btrfs=bool(btrfs.returncode)
        if uncertain_btrfs:
            try:uncertain_btrfs=any(' - btrfs ' in line for line in Path('/proc/self/mountinfo').read_text().splitlines())
            except OSError:pass
        btrfs_members={str(Path(match).resolve()) for match in re.findall(r'\bpath\s+(/dev/\S+)',btrfs.stdout)}
        links={}
        for path in sorted(Path('/dev/disk/by-id').glob('*'),key=lambda p:(not p.name.startswith('wwn-'),p.name)):
            if not re.search(r'-part\d+$',path.name):
                links.setdefault(str(path.resolve()),str(path))
        result=[]
        for disk in tree:
            if disk.get('type')!='disk' or not disk.get('size') or str(disk.get('path','')).startswith(('/dev/loop','/dev/nbd')):
                continue
            nodes=list(descendants(disk))
            mounted=any(any(m for m in (n.get('mountpoints') or [])) or n.get('fstype')=='swap' for n in nodes)
            mounted=mounted or any(str(Path(n['path']).resolve()) in btrfs_members for n in nodes)
            if uncertain_btrfs:
                mounted=mounted or any(n.get('fstype')=='btrfs' for n in nodes)
            held=any(any((Path('/sys/class/block')/Path(n['path']).name/'holders').glob('*')) for n in nodes)
            stable=links.get(disk['path'])
            recorded=self.app.config.get('storage',{}).get('disks',[])
            reserved=any(str(Path(member).resolve())==disk['path'] for member in recorded)
            reason='Mounted disk, operating system, or active storage' if mounted or held else 'Read-only disk' if disk.get('ro') else 'No stable disk identifier' if not stable else ''
            if not reason and reserved:reason='Recorded pool member — use Repair pool or Replace drive'
            result.append({'id':stable or disk['path'],'path':disk['path'],'size':disk['size'],
                'serial':str(disk.get('serial') or ''),'wwn':str(disk.get('wwn') or ''),'model':str(disk.get('model') or '').strip(),
                'eligible':not reason,'reason':reason,'existing_data':any(n.get('fstype') for n in nodes)})
        return result

    def assert_empty(self):
        if self.app.demo or os.getenv('HARBOR_LIVE')=='1':
            raise self.error('Install Harbor on a system disk before creating storage.',409)
        if self.app.storage_info()['mounted']:
            raise self.error('The primary data volume already exists. Existing storage is protected.',409)
        if self.app.config.get('storage',{}).get('uuid'):
            raise self.error('An existing pool is recorded but unavailable. Use Repair pool; do not create storage over its surviving disks.',409)

    def selection(self, ids, level):
        if not isinstance(ids,list) or not all(isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)):
            raise self.error('Select different available disks.')
        by_id={d['id']:d for d in self.inventory()}
        if any(i not in by_id or not by_id[i]['eligible'] for i in ids):
            raise self.error('A selected disk is in use, protected, or no longer present.',409)
        disks=[by_id[i] for i in ids]
        try:
            usable=capacity(level,[d['size'] for d in disks])
        except ValueError as error:
            raise self.error(str(error))
        return disks,usable

    def health(self, disks):
        unknown=[]
        for disk in disks:
            response=self.run('smartctl','-H','-A','-j',disk['id'],timeout=20,check=False)
            try:
                report=json.loads(response.stdout)
            except ValueError:
                report={}
            attributes=report.get('ata_smart_attributes',{}).get('table',[])
            bad=any(a.get('id') in (197,198) and a.get('raw',{}).get('value',0)>0 for a in attributes)
            if bad or report.get('smart_status',{}).get('passed') is False or report.get('nvme_smart_health_information_log',{}).get('critical_warning',0):
                raise self.error('Disk '+disk['serial']+' reports failing health or unreadable sectors. Replace it.',409)
            if 'smart_status' not in report:
                unknown.append(disk['id'])
        return unknown

    def plan(self,data):
        self.assert_empty()
        self.check_pending()
        name=data.get('name','')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}',name):
            raise self.error('Use a storage name with 1–32 letters, numbers, hyphens, or underscores.')
        level=str(data.get('level',''))
        disks,usable=self.selection(data.get('disks'),level)
        unknown=self.health(disks)
        token=secrets.token_urlsafe(24)
        self.plans={k:v for k,v in self.plans.items() if v['expires']>time.monotonic()}
        if len(self.plans)>=20:
            self.plans.pop(next(iter(self.plans)))
        self.plans[token]={'expires':time.monotonic()+300,'name':name,'level':level,'ids':[d['id'] for d in disks],
                           'identities':[identity(d) for d in disks]}
        return {'token':token,'name':name,'level':level,'disks':disks,'capacity':usable,'health_unknown':unknown,
                'confirmation':'ERASE '+name,'warning':'All files and partitions on the selected disks will be permanently erased.',
                'layout':layout(level,[d['size'] for d in disks]) if level in HYBRID_LEVELS else None}

    def create(self,data):
        with self.app.lock:
            plan=self.plans.get(data.get('token',''))
            if not plan or plan.get('kind')=='expand' or plan['expires']<time.monotonic():
                raise self.error('The disk plan expired. Review the disks again.',409)
            if data.get('confirmation')!='ERASE '+plan['name'] or data.get('acknowledge') is not True:
                raise self.error('Confirm erasure using the exact storage name.')
            plan=self.plans.pop(data['token'])
        if plan['level'] in HYBRID_LEVELS:return self.create_hybrid(plan)
        def execute():
            self.app.job_progress('Checking disks', 'Rechecking disk identities, health and system-disk protection.')
            self.assert_empty()
            self.check_pending()
            disks,_=self.selection(plan['ids'],plan['level'])
            if [identity(d) for d in disks]!=plan['identities']:
                raise self.error('Disk identities changed. No disks were modified.',409)
            self.health(disks)
            md=Path('/dev/md/harbor-data')
            md_needed=plan['level'] not in ('basic','linear')
            if md_needed and md.exists():
                raise self.error('An array already uses the Harbor data name.',409)
            # Recheck all eligibility immediately before the first destructive command.
            current,_=self.selection(plan['ids'],plan['level'])
            if [identity(d) for d in current]!=plan['identities']:
                raise self.error('Disk identities changed. No disks were modified.',409)
            self.app.job_progress('Preparing disks', 'Removing the old filesystem signatures from the confirmed disks.')
            for disk in current:
                self.run('wipefs','--all',disk['id'],timeout=30)
            device=current[0]['id']
            if md_needed:
                self.app.job_progress('Creating RAID array', 'Combining the selected disks using '+LEVELS[plan['level']]['name']+'.')
                self.run('mdadm','--create',str(md),'--metadata=1.2','--name=harbor-data',
                    '--level='+plan['level'],'--raid-devices='+str(len(current)),'--run',*plan['ids'],timeout=90)
                device=str(md)
            self.run('udevadm','settle',timeout=30)
            self.app.job_progress('Creating filesystem', 'Creating the Btrfs data filesystem.')
            if plan['level']=='linear':
                # Modern kernels removed MD linear; Btrfs single spans disk capacity.
                self.run('mkfs.btrfs','-f','-L','harbor-data','-d','single','-m','dup',*plan['ids'],timeout=300)
            else:
                self.run('mkfs.btrfs','-f','-L','harbor-data',device,timeout=300)
            uuid=self.run('blkid','-s','UUID','-o','value',device).stdout.strip()
            if not re.fullmatch(r'[a-fA-F0-9-]{36}',uuid):
                raise self.error('The filesystem UUID could not be verified.',409)
            fstab=Path('/etc/fstab')
            lines=[line for line in fstab.read_text().splitlines() if len(line.split())<2 or line.split()[1]!=str(self.app.storage)]
            lines.append(f'UUID={uuid} {self.app.storage} btrfs defaults,nofail,x-systemd.device-timeout=15 0 0')
            fstab.write_text('\n'.join(lines)+'\n')
            # PID 1 mounts in the host namespace so Docker and SMB see the volume.
            # The web service has a private mount namespace for its sandbox.
            self.run('systemctl','daemon-reload')
            self.app.job_progress('Mounting storage', 'Making the new storage available to file sharing and apps.')
            unit=self.run('systemd-escape','--path','--suffix=mount',str(self.app.storage)).stdout.strip()
            if not re.fullmatch(r'[A-Za-z0-9_.\\-]+\.mount',unit):
                raise self.error('The storage mount unit could not be verified.',409)
            self.run('systemctl','start',unit,timeout=90)
            if not self.app.storage_info()['mounted']:
                raise self.error('The system-managed storage mount did not become visible.',409)
            (self.app.storage/'shares').mkdir(exist_ok=True)
            (self.app.storage/'shares').chmod(0o755)
            if md_needed:
                self.app.job_progress('Saving boot configuration', 'Saving the RAID configuration so the array is available after a restart.')
                conf=Path('/etc/mdadm/mdadm.conf')
                scan=self.run('mdadm','--detail','--scan').stdout
                conf.write_text(conf.read_text()+'\n'+scan)
                # Rebuild outside the web sandbox, which hides kernel module files.
                self.run('systemd-run','--wait','--pipe','--collect','--unit=harbor-storage-initramfs',
                         '/usr/sbin/update-initramfs','-u',timeout=300)
            self.app.config['storage']={'name':plan['name'],'level':plan['level'],'uuid':uuid,'disks':plan['ids']}
            self.app.save()
            self.app.sync_samba()
            self.run('systemctl','daemon-reload')
            return self.app.storage_info()
        return self.app.job('Create '+LEVELS[plan['level']]['name']+' storage',execute,kind='storage',target=plan['name'])
