#!/usr/bin/env python3
"""Restricted, temporary SSH installer agent. Only the planned OS disk is writable."""
import hashlib,importlib.machinery,importlib.util,json,os,re,secrets,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
PLAN=Path('/etc/harbour-remote/plan.json')
def run(*args):return subprocess.check_output(args,text=True).strip()
def load_installer():
 loader=importlib.machinery.SourceFileLoader('remote_install','/usr/local/sbin/harbor-install');spec=importlib.util.spec_from_loader(loader.name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module);return module
def status(plan):
 try:
  with urllib.request.urlopen('http://127.0.0.1:17080/api/health',timeout=3) as response:health=json.load(response)
 except Exception:health=None
 storage=None
 if plan['phase']=='setup':
  sys.path.insert(0,'/opt/harbor')
  from server import Harbor
  app=Harbor()
  try:storage=app.storage_info()
  finally:app.pool.shutdown(wait=True)
 key=Path('/etc/ssh/ssh_host_ed25519_key.pub')
 return dict(phase=plan['phase'],disk=plan['disk'],pool=plan.get('pool'),storage=storage,health=health,native_ssh_host_key=key.read_text().strip() if key.exists() else None)
def check_efi_writes(plan):
 if not Path('/sys/firmware/efi').is_dir():return
 if not shutil.which('efibootmgr') or not isinstance(plan.get('efi_part'),int):raise ValueError('EFI boot registration preflight is unavailable. No disk was erased.')
 before=run('efibootmgr');order=re.search(r'^BootOrder: (.*)$',before,re.M)
 label='Harbour recovery check '+secrets.token_hex(6)
 output=run('efibootmgr','--create-only','--disk',plan['disk']['id'],'--part',str(plan['efi_part']),'--label',label,'--loader',r'\EFI\BOOT\BOOTX64.EFI')
 matches=re.findall(r'^Boot([0-9A-Fa-f]{4})\*?\s+'+re.escape(label)+r'\b',output,re.M)
 if len(matches)!=1:raise ValueError('The EFI test entry could not be identified. No disk was erased.')
 run('efibootmgr','--bootnum',matches[0],'--delete-bootnum')
 after=run('efibootmgr');next_order=re.search(r'^BootOrder: (.*)$',after,re.M)
 if not order or not next_order or order[1]!=next_order[1]:raise ValueError('EFI boot-order preflight changed unexpectedly. No disk was erased.')

def install(plan,data):
 if plan['phase']!='installer' or 'harbour.recovery=1' not in Path('/proc/cmdline').read_text().split():raise ValueError('Installation is available only in the RAM recovery environment.')
 if data.get('confirmation')!='ERASE '+plan['disk']['serial']:raise ValueError('Confirm the exact system-disk serial.')
 marker=Path('/run/harbour-remote-install-started')
 if marker.exists():raise ValueError('An installation already started; inspect its state before retrying.')
 module=load_installer();disk=next((d for d in module.inventory() if d['id']==plan['disk']['id']),None)
 if not disk or disk['id']!=plan['disk']['id'] or disk['size']!=plan['disk']['size'] or any(str(disk.get(k) or '')!=plan['disk'][k] for k in ('serial','wwn')):raise ValueError('The planned OS disk changed or is not available.')
 tree=json.loads(run('lsblk','-J','--tree','-p','-o','PATH,UUID',disk['id']))['blockdevices']
 def has_uuid(node):return node.get('uuid')==plan['old_root_uuid'] or any(has_uuid(c) for c in node.get('children',[]))
 if not any(has_uuid(n) for n in tree):raise ValueError('The original OS filesystem identity is absent. Refusing to erase a different installation.')
 check_efi_writes(plan)
 with marker.open('x') as stream:stream.write('started')
 module.install(disk)
 target=Path('/mnt/harbour-remote-new-system');target.mkdir(exist_ok=True)
 subprocess.run(['mount',disk['id']+'-part3',str(target)],check=True)
 try:
  for relative in ('etc/ssh/harbour-recovery-host-key','etc/ssh/harbour-recovery-authorized_keys','etc/ssh/sshd_config.d/00-harbour-remote.conf','etc/systemd/network/20-wired.network','usr/local/sbin/harbour-remote-agent'):
   source=Path('/')/relative;destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
  folder=target/'etc/harbour-remote';folder.mkdir(mode=0o700,exist_ok=True);updated=dict(plan,phase='setup');(folder/'plan.json').write_text(json.dumps(updated));(folder/'plan.json').chmod(0o600)
  cleanup=target/'usr/local/sbin/harbour-remote-cleanup';cleanup.write_text('''#!/bin/sh
set -eu
test -f /var/lib/harbor/admin.json || exit 0
rm -f /etc/ssh/harbour-recovery-authorized_keys /etc/ssh/harbour-recovery-host-key /etc/ssh/sshd_config.d/00-harbour-remote.conf /etc/harbour-remote/plan.json
ssh-keygen -A
systemctl reload ssh
''');cleanup.chmod(0o700)
  (target/'etc/systemd/system/harbour-remote-cleanup.service').write_text('[Unit]\nDescription=Remove temporary remote installation access after owner setup\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/local/sbin/harbour-remote-cleanup\n')
  (target/'etc/systemd/system/harbour-remote-cleanup.path').write_text('[Unit]\nDescription=Watch for graphical owner setup\n[Path]\nPathExists=/var/lib/harbor/admin.json\nUnit=harbour-remote-cleanup.service\n[Install]\nWantedBy=multi-user.target\n')
  wants=target/'etc/systemd/system/multi-user.target.wants';wants.mkdir(exist_ok=True);link=wants/'harbour-remote-cleanup.path';link.unlink(missing_ok=True);link.symlink_to('../harbour-remote-cleanup.path')
  if Path('/sys/firmware/efi').is_dir():subprocess.run(['efibootmgr','--create','--disk',disk['id'],'--part','2','--label','Harbour OS','--loader',r'\EFI\BOOT\BOOTX64.EFI'],check=True)
  subprocess.run(['sync','-f',str(target)],check=True)
 finally:subprocess.run(['umount',str(target)],check=True)
 plan['phase']='installed';PLAN.write_text(json.dumps(plan));return {'phase':'installed','message':'Fresh Harbour installed; temporary setup access provisioned.'}
def create_pool(plan,data):
 pool=plan.get('pool')
 if plan['phase']!='setup' or not pool or pool['mode']!='hybrid1':raise ValueError('No data-pool reset is authorized in this phase.')
 if data.get('confirmation')!='ERASE POOL '+pool['name']:raise ValueError('Confirm the exact planned pool erase.')
 if Path('/var/lib/harbor/admin.json').exists():raise ValueError('Configure the pool before first-owner setup, or use the authenticated web interface afterward.')
 if Path('/var/lib/harbor/remote-pool-started').exists():raise ValueError('A pool reset already started. Inspect its journal before retrying.')
 sys.path.insert(0,'/opt/harbor')
 from server import Harbor
 app=Harbor()
 try:
  inventory=app.storage_manager.inventory();ids=[]
  for expected in pool['disks']:
   disk=next((d for d in inventory if d['id']==expected['id']),None)
   if not disk or any(disk[k]!=expected[k] for k in ('id','size','serial','wwn')) or not disk['eligible']:raise ValueError('A planned data disk changed or is protected.')
   if run('blkid','-s','UUID','-o','value',disk['id'])!=pool['old_uuid']:raise ValueError('The original data-pool UUID changed. Refusing a different pool.')
   ids.append(disk['id'])
  review=app.storage_manager.plan({'level':'hybrid1','name':pool['name'],'disks':ids})
  Path('/var/lib/harbor/remote-pool-started').write_text('started')
  # No shares are exported until the new owner is created by graphical setup.
  app.sync_samba=lambda:None
  job=app.storage_manager.create({'token':review['token'],'confirmation':review['confirmation'],'acknowledge':True})
  last=None
  while app.jobs[job['id']]['state'] in ('queued','running'):
   value=app.jobs[job['id']]
   if value.get('stage')!=last:print(value.get('stage','Starting pool'),flush=True);last=value.get('stage')
   time.sleep(1)
  value=app.jobs[job['id']]
  if value['state']!='completed':raise ValueError(value.get('error','Pool creation stopped.'))
  plan['pool_completed']=True;PLAN.write_text(json.dumps(plan))
 finally:app.pool.shutdown(wait=True)
 subprocess.run(['systemctl','restart','harbor'],check=True)
 return {'phase':'setup','pool_created':True,'mode':'hybrid1','name':pool['name']}

def main():
 if os.geteuid()!=0:raise ValueError('The remote agent requires its restricted root SSH context.')
 plan=json.loads(PLAN.read_text());command=os.environ.get('SSH_ORIGINAL_COMMAND','').strip()
 if command=='status':result=status(plan)
 elif command=='install':result=install(plan,json.loads(sys.stdin.readline()))
 elif command=='create-pool':result=create_pool(plan,json.loads(sys.stdin.readline()))
 elif command=='reboot':
  if plan['phase']!='installed':raise ValueError('Reboot is allowed only after a completed installation.')
  subprocess.run(['systemd-run','--on-active=5','--unit=harbour-remote-finish','/usr/bin/systemctl','reboot'],check=True);result={'phase':'rebooting'}
 else:raise ValueError('Only status, planned installation, planned pool creation and post-install reboot are allowed.')
 print(json.dumps(result),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as error:print(json.dumps({'error':str(error)}),flush=True);raise SystemExit(1)
