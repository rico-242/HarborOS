"""Boot a release ISO as read-only USB media in disposable BIOS and UEFI VMs."""
import argparse,base64,json,os,shutil,socket,subprocess,tempfile,time
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('iso',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
version=subprocess.check_output(['python3',str(root/'tools/release-version.py')],text=True).strip()
iso=args.iso.resolve();assert iso.is_file()
script='''import json,urllib.request,subprocess,hashlib
from pathlib import Path
assert 'boot=live' in Path('/proc/cmdline').read_text().split()
health=json.load(urllib.request.urlopen('http://127.0.0.1:17080/api/health'))
installer=json.load(urllib.request.urlopen('http://127.0.0.1:17081/api/status'))
assert health['version']==VERSION and installer['version']==VERSION
assert health['live'] and health['setup_required'] and installer['phase']=='ready'
assert not Path('/var/lib/harbor/admin.json').exists()
assert not Path('/etc/harbour-remote/plan.json').exists()
assert not Path('/etc/ssh/harbour-recovery-authorized_keys').exists()
assert not Path('/var/lib/harbor/release-updates/github-credential.json').exists()
assert subprocess.check_output(['systemctl','is-active','lightdm','harbor','harbor-installer'],text=True).split()==['active']*3
for asset in ('clarity.css','recovery.js','theme.js','experience.css','experience.js','wallpaper.svg','catalog/icons/featured-blinko.png'):
 assert urllib.request.urlopen('http://127.0.0.1:17080/'+asset).status==200,asset
for asset in ('','install.js','theme.js','experience.css'):
 assert urllib.request.urlopen('http://127.0.0.1:17081/'+asset).status==200,asset
assert hashlib.sha256(Path('/etc/harbor/update-public.pem').read_bytes()).hexdigest()==KEY
import sys,shutil
sys.path.insert(0,'/opt/harbor')
from hybrid_layout import HYBRID_LEVELS
from drive_lifecycle import DriveLifecycle
assert set(HYBRID_LEVELS)=={'hybrid1','hybrid2'}
import tempfile
from appstore import prepare,provision_app_mounts
with tempfile.TemporaryDirectory(dir='/run',prefix='harbour-app-storage-') as directory:
 root=Path(directory);apps=root/'apps';storage=root/'storage'
 prepared=prepare('anythingllm',str(apps),str(storage))
 provision_app_mounts('anythingllm',prepared['compose'],apps,storage)
 info=(apps/'anythingllm/storage').stat()
 assert info.st_uid==1000 and info.st_gid==1000 and info.st_mode&0o700==0o700

assert all(shutil.which(name) for name in ('mdadm','parted','btrfs','wipefs','xorriso','grub-reboot','grub-editenv','efibootmgr','ssh-keygen','unmkinitramfs'))
print(json.dumps({'version':VERSION,'live':True,'graphical_services':True,'installer_ready':True,'fresh_owner':True,'public_update_key':True,'assets_http_200':True,'uefi':Path('/sys/firmware/efi').exists(),'disk_wipe_acceptance':True,'ai_app_storage_acceptance':True}))
'''
script=script.replace('print(json.dumps(', "Path('/run/disk-wipe-live-test.py').write_text("+repr((root/'tools/test-disk-wipe-live.py').read_text())+")\nimport runpy\nrunpy.run_path('/run/disk-wipe-live-test.py')\nprint(json.dumps(",1)
script='VERSION='+repr(version)+'\nKEY='+repr(__import__('hashlib').sha256((root/'os/release-public.pem').read_bytes()).hexdigest())+'\n'+script

def agent(path,name,arguments=None):
 with socket.socket(socket.AF_UNIX) as sock:
  sock.settimeout(20);sock.connect(str(path));stream=sock.makefile('rwb',buffering=0)
  stream.write((json.dumps({'execute':name,'arguments':arguments or {}})+'\n').encode())
  while True:
   line=stream.readline()
   if not line:raise RuntimeError('Guest agent disconnected')
   value=json.loads(line)
   if 'error' in value:raise RuntimeError(value['error'])
   if 'return' in value:return value['return']

results={}
for firmware in ('bios','uefi'):
 with tempfile.TemporaryDirectory(prefix='harbour-iso-') as directory:
  d=Path(directory);agent_path=d/'agent.sock'
  command=['qemu-system-x86_64','-machine','q35','-m','4096','-smp','2','-display','none','-no-reboot','-netdev','user,id=net0','-device','virtio-net-pci,netdev=net0','-device','qemu-xhci','-drive',f'if=none,id=usbmedia,format=raw,readonly=on,file={iso}','-device','usb-storage,drive=usbmedia,bootindex=1','-device','virtio-serial-pci','-chardev',f'socket,path={agent_path},server=on,wait=off,id=agent0','-device','virtserialport,chardev=agent0,name=org.qemu.guest_agent.0','-serial',f'file:{d}/serial.log']
  if os.access('/dev/kvm',os.R_OK|os.W_OK):command+=['-enable-kvm','-cpu','host']
  else:command+=['-accel','tcg,thread=multi']
  if firmware=='uefi':
   ovmf=Path('/usr/share/OVMF');shutil.copyfile(ovmf/'OVMF_VARS_4M.fd',d/'vars.fd')
   command+=['-drive',f'if=pflash,format=raw,readonly=on,file={ovmf}/OVMF_CODE_4M.fd','-drive',f'if=pflash,format=raw,file={d}/vars.fd']
  with (d/'qemu.log').open('wb') as log:
   process=subprocess.Popen(command,stdout=log,stderr=log)
   try:
    deadline=time.monotonic()+600;last='Guest agent not ready'
    while time.monotonic()<deadline:
     if process.poll() is not None:raise RuntimeError((d/'qemu.log').read_text())
     try:
      agent(agent_path,'guest-ping')
      task=agent(agent_path,'guest-exec',{'path':'/usr/bin/python3','arg':['-c',script],'capture-output':True})
      while time.monotonic()<deadline:
       status=agent(agent_path,'guest-exec-status',{'pid':task['pid']})
       if status['exited']:break
       time.sleep(1)
      if not status.get('exited'):raise RuntimeError('Guest check timed out')
      out=base64.b64decode(status.get('out-data','')).decode();err=base64.b64decode(status.get('err-data','')).decode()
      if status.get('exitcode')!=0:
       if 'disk-wipe-live-test.py' in err:raise AssertionError(err)
       raise RuntimeError(err or out)
      value=json.loads(out);assert value['uefi']==(firmware=='uefi')
      results[firmware]=value;print(firmware+': '+out,flush=True);break
     except (OSError,RuntimeError,ValueError) as error:
      if str(error)!=last:print(firmware+': waiting: '+str(error),flush=True)
      last=str(error);time.sleep(3)
    else:raise RuntimeError(f'{firmware} boot check failed: {last}\n'+(d/'serial.log').read_text(errors='replace')[-5000:])
   finally:
    process.terminate()
    try:process.wait(timeout=20)
    except subprocess.TimeoutExpired:process.kill();process.wait()
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({'version':version,'read_only_usb_boot':results},indent=2)+'\n')
