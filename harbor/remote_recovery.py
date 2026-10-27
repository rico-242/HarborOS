"""Build an owner-authorized, restricted SSH bridge into signed RAM recovery."""
import base64,gzip,hashlib,ipaddress,json,os,re,stat,struct,subprocess,sys,tempfile
from pathlib import Path
from hybrid_storage import atomic_text
from recovery import Recovery,verify_manifest

def cpio_archive(files):
 output=bytearray();inode=1
 for name,data,mode in [*files,('TRAILER!!!',b'',0)]:
  encoded=name.encode()+b'\0';fields=(inode,mode,0,0,1,0,len(data),0,0,0,0,len(encoded),0);inode+=1
  output.extend(b'070701'+b''.join(('%08x'%v).encode() for v in fields));output.extend(encoded);output.extend(b'\0'*((-len(output))%4));output.extend(data);output.extend(b'\0'*((-len(output))%4))
 return gzip.compress(bytes(output),mtime=0)

def network_snapshot(run,server_ip=None):
 routes=json.loads(run('ip','-j','-4','route','show','default').stdout)
 if not routes:raise ValueError('A direct IPv4 default route is required for headless installation.')
 route=min(routes,key=lambda item:item.get('metric',0));name=route['dev']
 if not (Path('/sys/class/net')/name/'device').exists() or (Path('/sys/class/net')/name/'wireless').exists():raise ValueError('Headless installation currently requires a direct physical Ethernet adapter.')
 data=json.loads(run('ip','-j','-4','address','show','dev',name).stdout)[0]
 addresses=[a for a in data['addr_info'] if a.get('scope')=='global' and a.get('family')=='inet']
 address=next((a for a in addresses if server_ip is None or a['local']==server_ip),None)
 if not address:raise ValueError('The SSH address is not on the direct default-route adapter.')
 interface=ipaddress.IPv4Interface(address['local']+'/'+str(address['prefixlen']));gateway=ipaddress.IPv4Address(route['gateway'])
 if gateway not in interface.network:raise ValueError('An off-subnet gateway requires another recovery method.')
 mac=(Path('/sys/class/net')/name/'address').read_text().strip().lower()
 if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',mac):raise ValueError('A stable Ethernet address is required.')
 permanent=run('ethtool','-P',name,check=False).stdout.strip().split()
 if permanent and re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',permanent[-1].lower()) and permanent[-1].lower() not in (mac,'00:00:00:00:00:00'):raise ValueError('Headless installation does not support a spoofed Ethernet address.')
 dns=[];resolv=Path('/run/systemd/resolve/resolv.conf')
 if resolv.exists():
  for value in re.findall(r'^nameserver\s+(\S+)',resolv.read_text(),re.M):
   try:
    item=ipaddress.ip_address(value)
    if isinstance(item,ipaddress.IPv4Address) and not item.is_loopback:dns.append(str(item))
   except ValueError:pass
 return dict(mac=mac,address=str(interface),gateway=str(gateway),dns=dns[:3] or [str(gateway)])

def network_configuration(network):
 return '[Match]\nMACAddress='+network['mac']+'\n\n[Network]\nDHCP=no\nMulticastDNS=yes\nIPv6AcceptRA=yes\nAddress='+network['address']+'\nGateway='+network['gateway']+'\n'+''.join('DNS='+address+'\n' for address in network['dns'])

def stage(app,run,error,version,client_key,pool=None,server_ip=None):
 if os.geteuid()!=0:raise error('Root SSH administration is required.',403)
 if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]{60,100}={0,2}',client_key):raise error('Use an Ed25519 public key.')
 recovery=Recovery(app,run,error,version);fs=recovery.supported();root=recovery.root
 ready=json.loads((root/'ready.json').read_text());manifest=verify_manifest(json.loads((root/'signed-manifest.json').read_text()),recovery.key)
 if ready['version']!=version or manifest['version']!=version:raise error('Prepare the matching signed image first.',409)
 with (root/'recovery.iso').open('rb') as stream:
  if hashlib.file_digest(stream,'sha256').hexdigest()!=manifest['sha256']:raise error('The recovery image changed.',409)
 source=fs['source'].split('[')[0];ancestry=run('lsblk','-s','-l','-n','-p','-o','TYPE,PATH',source).stdout
 parents=[line.split()[1] for line in ancestry.splitlines() if line.split()[0]=='disk']
 if len(parents)!=1:raise error('The system disk could not be identified.',409)
 disk=next(d for d in app.storage_manager.inventory() if d['path']==parents[0])
 if not disk['id'].startswith('/dev/disk/by-id/') or not disk['serial']:raise error('A stable system-disk ID and serial are required.',409)
 network=network_snapshot(run,server_ip)
 plan=dict(phase='installer',network=network,disk={k:disk[k] for k in ('id','size','serial','wwn')},old_root_uuid=fs['uuid'])
 if Path('/sys/firmware/efi').is_dir():
  esp=json.loads(run('findmnt','-J','-T','/boot/efi','-o','SOURCE,TARGET,FSTYPE').stdout)['filesystems'][0]
  if esp['target']!='/boot/efi' or esp['fstype']!='vfat':raise error('The system EFI partition must be mounted.',409)
  esp_source=esp['source'].split('[')[0]
  esp_parents=run('lsblk','-s','-l','-n','-p','-o','TYPE,PATH',esp_source).stdout
  if parents[0] not in [line.split()[1] for line in esp_parents.splitlines() if line.split()[0]=='disk']:raise error('The EFI partition is on another physical disk.',409)
  plan['efi_part']=int((Path('/sys/class/block')/Path(esp_source).resolve().name/'partition').read_text())
 if pool is not None:
  if pool!='hybrid1':raise error('Only the explicitly planned Hybrid1 reset is supported.',409)
  current=app.storage_manager.lifecycle_state()
  if current['mode']!='native-raid1' or len(current['members'])!=2 or any(m['missing'] for m in current['members']):raise error('Automatic pool reset requires the current healthy two-disk native mirror.',409)
  ids=[m['disk_id'] for m in current['members']]
  chosen=[d for d in app.storage_manager.inventory() if d['id'] in ids]
  if len(chosen)!=2 or disk['id'] in ids:raise error('The data disks could not be distinguished from the system SSD.',409)
  app.storage_manager.health(chosen)
  plan['pool']=dict(mode='hybrid1',name='Main-Storage',old_uuid=current['uuid'],disks=[{k:d[k] for k in ('id','size','serial','wwn')} for d in chosen])
 key=root/'remote-host-key'
 for path in (key,Path(str(key)+'.pub')):path.unlink(missing_ok=True)
 run('ssh-keygen','-q','-t','ed25519','-N','','-f',str(key))
 authorized='restrict,port-forwarding,permitopen="127.0.0.1:17080",command="/usr/local/sbin/harbour-remote-agent" '+client_key+'\n'
 config='HostKey /etc/ssh/harbour-recovery-host-key\nAuthorizedKeysFile /etc/ssh/harbour-recovery-authorized_keys\nPermitRootLogin prohibit-password\nAuthenticationMethods publickey\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nAllowUsers root\n'
 hook='''#!/bin/sh
case "${1:-}" in prereqs) exit 0;; esac
set -eu
target=${rootmnt:-/root}
mkdir -p "$target/etc/ssh/sshd_config.d" "$target/etc/systemd/network" "$target/etc/harbour-remote" "$target/usr/local/sbin" "$target/etc/systemd/system/multi-user.target.wants"
cp /harbour-remote/host-key "$target/etc/ssh/harbour-recovery-host-key"
cp /harbour-remote/authorized-keys "$target/etc/ssh/harbour-recovery-authorized_keys"
cp /harbour-remote/network.conf "$target/etc/systemd/network/20-wired.network"
cp /harbour-remote/sshd.conf "$target/etc/ssh/sshd_config.d/00-harbour-remote.conf"
cp /harbour-remote/plan.json "$target/etc/harbour-remote/plan.json"
cp /harbour-remote/agent "$target/usr/local/sbin/harbour-remote-agent"
chmod 600 "$target/etc/ssh/harbour-recovery-host-key" "$target/etc/ssh/harbour-recovery-authorized_keys" "$target/etc/harbour-remote/plan.json"
chmod 700 "$target/etc/harbour-remote" "$target/usr/local/sbin/harbour-remote-agent"
ln -sf /lib/systemd/system/ssh.service "$target/etc/systemd/system/multi-user.target.wants/ssh.service"
'''
 with tempfile.TemporaryDirectory(dir=root) as temporary:
  run('unmkinitramfs',str(root/'initrd.img'),temporary,timeout=120)
  orders=list(Path(temporary).glob('**/scripts/init-bottom/ORDER'))
  if len(orders)!=1:raise error('The live initramfs hook order could not be identified.',409)
  order=orders[0].read_bytes()+b'\n/scripts/init-bottom/99-harbour-remote \"$@\"\n'
 files=[('scripts/init-bottom/ORDER',order,stat.S_IFREG|0o755),('harbour-remote',b'',stat.S_IFDIR|0o700),('harbour-remote/host-key',key.read_bytes(),stat.S_IFREG|0o600),('harbour-remote/authorized-keys',authorized.encode(),stat.S_IFREG|0o600),('harbour-remote/sshd.conf',config.encode(),stat.S_IFREG|0o600),('harbour-remote/plan.json',json.dumps(plan).encode(),stat.S_IFREG|0o600),('harbour-remote/network.conf',network_configuration(network).encode(),stat.S_IFREG|0o600),('harbour-remote/agent',Path(__file__).with_name('remote_agent.py').read_bytes(),stat.S_IFREG|0o700),('scripts/init-bottom/99-harbour-remote',hook.encode(),stat.S_IFREG|0o755)]
 overlay=root/'remote-initrd.img';overlay.write_bytes(cpio_archive(files));overlay.chmod(0o600)
 path=Path(fs['grub_config']);original=path.read_text();line='  initrd '+fs['image_prefix']+'/boot/harbour-recovery/initrd.img'
 original=re.sub(re.escape(line)+r'(?: [^\n]+)?',line,original)
 if original.count(line)!=1:raise error('The recovery entry is unavailable.',409)
 generated=original.replace(line,line+' '+fs['image_prefix']+'/boot/harbour-recovery/remote-initrd.img')
 trial=root/'remote-grub-check.cfg';atomic_text(trial,generated);run('grub-script-check',str(trial));atomic_text(path,generated)
 record=dict(plan=plan,overlay_sha256=hashlib.sha256(overlay.read_bytes()).hexdigest(),server_key=Path(str(key)+'.pub').read_text().strip())
 atomic_text(root/'remote-plan.json',json.dumps(record));return record

def arm(app,run,error,version):
 recovery=Recovery(app,run,error,version);fs=recovery.supported();root=recovery.root;record=json.loads((root/'remote-plan.json').read_text())
 if hashlib.sha256((root/'remote-initrd.img').read_bytes()).hexdigest()!=record['overlay_sha256']:raise error('The remote bootstrap changed.',409)
 manifest=verify_manifest(json.loads((root/'signed-manifest.json').read_text()),recovery.key)
 with (root/'recovery.iso').open('rb') as stream:
  if hashlib.file_digest(stream,'sha256').hexdigest()!=manifest['sha256'] or manifest['version']!=version:raise error('The signed recovery image changed.',409)
 if fs['legacy']:run('grub-editenv',fs['grub_env'],'set','harbour_recovery_once=1')
 else:run('grub-reboot','harbour-recovery')
 run('systemd-run','--on-active=5','--unit=harbour-remote-recovery','/usr/bin/systemctl','reboot')
 return {'phase':'rebooting','disk':record['plan']['disk']}

if __name__=='__main__':
 from server import Harbor,run,APIError,VERSION
 app=Harbor()
 try:
  if sys.argv[1]=='stage':data=json.loads(sys.stdin.readline());result=stage(app,run,APIError,VERSION,data['client_key'],data.get('pool'),data.get('server_ip'))
  elif sys.argv[1]=='arm':result=arm(app,run,APIError,VERSION)
  else:raise ValueError('Choose stage or arm.')
  print(json.dumps(result),flush=True)
 finally:app.pool.shutdown(wait=True)
