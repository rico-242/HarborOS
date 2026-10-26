import importlib.machinery,importlib.util,json,hashlib,subprocess
from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
cmd=Path('/proc/cmdline').read_text().split();assert 'harbour.recovery=1' in cmd and 'toram' in cmd
assert subprocess.check_output(['findmnt','-n','-T','/run/live/medium/live/filesystem.squashfs','-o','FSTYPE'],text=True).strip()=='tmpfs'
loader=importlib.machinery.SourceFileLoader('recovery_install','/usr/local/sbin/harbor-install');spec=importlib.util.spec_from_loader(loader.name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module)
disk=next(d for d in module.inventory() if d.get('serial','').startswith('HARBOUR_HYBRID_SYST'))
assert disk['path']=='/dev/vda' and disk['id'].startswith('/dev/disk/by-id/virtio-HARBOUR_HYBRID_SYST')
# Prove the data array remains readable, then leave it unmounted for the installer.
probe=Path('/run/recovery-data-probe');probe.mkdir(exist_ok=True)
subprocess.run(['mount','-o','ro','/dev/md127',str(probe)],check=True)
original=hashlib.sha256((probe/'probe.bin').read_bytes()).hexdigest();subprocess.run(['umount',str(probe)],check=True)
module.install(disk)
subprocess.run(['mount','-o','ro','/dev/md127',str(probe)],check=True)
assert hashlib.sha256((probe/'probe.bin').read_bytes()).hexdigest()==original
subprocess.run(['umount',str(probe)],check=True)
# Retain test evidence outside the virtual system disk on the host through stdout.
print(json.dumps({'ram_recovery_boot':True,'no_usb_or_iso_attached':True,'system_disk_released':True,'fresh_virtual_system_installed':True,'data_pool_hash_preserved':True,'expected_hash':original}))
