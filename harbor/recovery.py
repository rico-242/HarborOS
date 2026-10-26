"""Stage a signed, RAM-booted fresh installer. Staging never erases disks."""
import base64,hashlib,json,os,re,shutil,subprocess,time,urllib.request
from pathlib import Path
from hybrid_storage import atomic_text

MAX_IMAGE=4*1024**3
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def verify_manifest(envelope,key):
 manifest=envelope['manifest'];raw=canonical(manifest)
 if manifest.get('product')!='harbour-recovery' or manifest.get('architecture')!='amd64' or not re.fullmatch(r'\d+\.\d+\.\d+',manifest.get('version','')):raise ValueError('Invalid recovery image metadata.')
 if not isinstance(manifest.get('size'),int) or not 100*1024**2<=manifest['size']<=MAX_IMAGE or not re.fullmatch('[a-f0-9]{64}',manifest.get('sha256','')):raise ValueError('Invalid recovery image size or checksum.')
 if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/v'+re.escape(manifest['version'])+r'/harbour-'+re.escape(manifest['version'])+r'-amd64\.iso',manifest.get('url','')):raise ValueError('Invalid recovery image URL.')
 signature=base64.b64decode(envelope['signature'],validate=True)
 if len(signature)!=64:raise ValueError('Invalid recovery signature.')
 import tempfile
 with tempfile.TemporaryDirectory() as folder:
  root=Path(folder);(root/'manifest').write_bytes(raw);(root/'signature').write_bytes(signature)
  try:
   result=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(key),'-rawin','-in',str(root/'manifest'),'-sigfile',str(root/'signature')],capture_output=True)
   if result.returncode:raise ValueError('The recovery image was not signed by the trusted Harbour key.')
  except FileNotFoundError:
   from cryptography.hazmat.primitives import serialization
   try:serialization.load_pem_public_key(Path(key).read_bytes()).verify(signature,raw)
   except Exception:raise ValueError('The recovery image was not signed by the trusted Harbour key.') from None
 return manifest

def grub_configuration(original,uuid):
 if not re.fullmatch('[a-fA-F0-9-]{36}',uuid) or 'root=UUID='+uuid not in original or '/boot/harbor-vmlinuz' not in original:raise ValueError('Only Harbour’s standard ext4 system boot configuration is supported.')
 marker='\n# HARBOUR RECOVERY START\n'
 original=original.split(marker)[0]
 if '# HARBOUR ONE-TIME BOOT' not in original:
  if 'set default=0' not in original:raise ValueError('The standard Harbour boot default is unavailable.')
  original=original.replace('set default=0','''# HARBOUR ONE-TIME BOOT
if [ -s $prefix/grubenv ]; then load_env; fi
if [ "${next_entry}" ]; then
  set default="${next_entry}"
  set next_entry=
  save_env next_entry
else
  set default=0
fi''',1)
 return original+marker+'''menuentry 'Harbour recovery — fresh installation' --id harbour-recovery {
  search --no-floppy --fs-uuid --set=root '''+uuid+'''
  linux /boot/harbour-recovery/vmlinuz boot=live components nopersistence noeject toram findiso=/boot/harbour-recovery/recovery.iso harbour.recovery=1 quiet splash console=tty0 console=ttyS0,115200n8
  initrd /boot/harbour-recovery/initrd.img
}
# HARBOUR RECOVERY END
'''

class Recovery:
 def __init__(self,app,run,error,current):
  self.app,self.run,self.error,self.current=app,run,error,current
  self.root=app.state/'recovery-preview' if app.demo else Path('/boot/harbour-recovery')
  self.key=Path('/etc/harbor/update-public.pem')
 def supported(self):
  if self.app.demo or os.getenv('HARBOR_LIVE')=='1':raise self.error('Recovery preparation requires an installed Harbour system.',409)
  fs=json.loads(self.run('findmnt','-J','-T','/','-o','SOURCE,FSTYPE,UUID,TARGET').stdout)['filesystems'][0]
  if fs['fstype']!='ext4' or fs['target']!='/' or not fs.get('uuid'):raise self.error('Recovery currently requires the standard ext4 Harbour installation.',409)
  if Path('/boot').stat().st_dev!=Path('/').stat().st_dev:raise self.error('Recovery requires /boot on the system filesystem.',409)
  if not all(shutil.which(name) for name in ('xorriso','grub-reboot','grub-editenv','grub-script-check','openssl')):raise self.error('Recovery tools are unavailable. Install the Harbour recovery tools first.',409)
  return fs
 def info(self):
  try:fs=self.supported();supported=True;reason=''
  except Exception as error:supported=False;reason=str(error)
  prepared=None
  if (self.root/'ready.json').exists():
   try:prepared=json.loads((self.root/'ready.json').read_text())
   except (ValueError,OSError):pass
  return dict(supported=supported,reason=reason,prepared=prepared,requires_local_screen=True,warning='Fresh installation erases the selected system disk, including System SSD files, apps, accounts and settings. Data-pool disks are separate and are not erased by preparation or recovery boot.')
 def prepare(self):
  fs=self.supported()
  def execute():
   config,_=self.app.releases.source();repo=config.get('repository','rico-242/HarborOS')
   if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise self.error('Configure a public GitHub repository first.',409)
   url='https://github.com/'+repo+'/releases/download/v'+self.current+'/harbour-recovery.json'
   self.app.job_progress('Checking recovery signature','Downloading the recovery manifest for Harbour '+self.current+'.')
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Harbour-recovery'}),timeout=30) as response:
    raw=response.read(65537)
   if len(raw)>65536:raise self.error('The recovery manifest is too large.',409)
   envelope=json.loads(raw);manifest=verify_manifest(envelope,self.key)
   if manifest['version']!=self.current:raise self.error('The recovery image version differs from this installed release.',409)
   memory=int(re.search(r'MemTotal:\s+(\d+)',Path('/proc/meminfo').read_text())[1])*1024
   if memory<manifest['size']*2+2*1024**3:raise self.error('There is not enough RAM to release the system disk safely for reinstallation.',409)
   self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
   if self.root.is_symlink() or self.root.stat().st_dev!=Path('/').stat().st_dev:raise self.error('Recovery staging is redirected or on another filesystem.',409)
   if shutil.disk_usage(self.root).free<manifest['size']+1024**3:raise self.error('Free additional space on the system SSD before preparing recovery.',409)
   (self.root/'ready.json').unlink(missing_ok=True)
   temporary=self.root/'recovery.iso.part';digest=hashlib.sha256();count=0
   try:
    with urllib.request.urlopen(urllib.request.Request(manifest['url'],headers={'User-Agent':'Harbour-recovery'}),timeout=60) as response,temporary.open('wb') as output:
     if response.headers.get('Content-Length') and int(response.headers['Content-Length'])!=manifest['size']:raise ValueError('Recovery download size differs from the signed record.')
     last=0
     while chunk:=response.read(1024**2):
      count+=len(chunk)
      if count>manifest['size']:raise ValueError('Recovery image exceeds its signed size.')
      output.write(chunk);digest.update(chunk)
      if time.monotonic()-last>1:self.app.job_progress('Downloading recovery image',str(count)+' / '+str(manifest['size'])+' bytes');last=time.monotonic()
     output.flush();os.fsync(output.fileno())
    if count!=manifest['size'] or digest.hexdigest()!=manifest['sha256']:raise ValueError('Recovery image checksum verification failed.')
    temporary.replace(self.root/'recovery.iso')
   finally:temporary.unlink(missing_ok=True)
   self.app.job_progress('Preparing recovery boot','Extracting the verified kernel and initial filesystem. Normal boot remains selected.')
   for name in ('vmlinuz','initrd.img'):
    destination=self.root/name;destination.unlink(missing_ok=True)
    self.run('xorriso','-osirrox','on','-indev',str(self.root/'recovery.iso'),'-extract','/live/'+name,str(destination),timeout=120)
   config_path=Path('/boot/grub/grub.cfg');original=config_path.read_text();generated=grub_configuration(original,fs['uuid'])
   trial=self.root/'grub.cfg.check';atomic_text(trial,generated);self.run('grub-script-check',str(trial))
   if not (self.root/'grub.cfg.backup').exists():atomic_text(self.root/'grub.cfg.backup',original)
   atomic_text(config_path,generated)
   if not Path('/boot/grub/grubenv').exists():self.run('grub-editenv','/boot/grub/grubenv','create')
   hashes={name:hashlib.sha256((self.root/name).read_bytes()).hexdigest() for name in ('vmlinuz','initrd.img')}
   atomic_text(self.root/'signed-manifest.json',json.dumps(envelope))
   atomic_text(self.root/'ready.json',json.dumps(dict(version=self.current,sha256=manifest['sha256'],size=count,kernel_hashes=hashes,root_uuid=fs['uuid'])))
   return self.info()
  return self.app.job('Prepare fresh OS installation',execute,kind='recovery')
 def boot(self,data):
  fs=self.supported()
  if data.get('confirmation')!='BOOT RECOVERY' or data.get('local_screen') is not True:raise self.error('Confirm BOOT RECOVERY and access to a connected monitor and keyboard.',409)
  def execute():
   ready=json.loads((self.root/'ready.json').read_text());manifest=verify_manifest(json.loads((self.root/'signed-manifest.json').read_text()),self.key)
   if manifest['version']!=self.current or ready['root_uuid']!=fs['uuid'] or ready['sha256']!=manifest['sha256']:raise self.error('Recovery staging differs from the signed image.',409)
   self.app.job_progress('Verifying staged recovery','Checking the image again before selecting a one-time boot.')
   with (self.root/'recovery.iso').open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
   if digest!=manifest['sha256']:raise self.error('The staged recovery image changed. Prepare it again.',409)
   for name,digest in ready['kernel_hashes'].items():
    if name not in ('vmlinuz','initrd.img') or hashlib.sha256((self.root/name).read_bytes()).hexdigest()!=digest:raise self.error('The staged recovery kernel changed.',409)
   self.run('grub-reboot','harbour-recovery')
   self.run('systemd-run','--on-active=5','--unit=harbour-enter-recovery','/usr/bin/systemctl','reboot')
   return {'message':'Restarting into the local graphical installer. No disk is erased until you confirm its installation there.'}
  return self.app.job('Boot recovery installer',execute,kind='recovery')
