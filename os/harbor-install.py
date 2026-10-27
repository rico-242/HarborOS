#!/usr/bin/env python3
"""Interactive offline installer. Run only from Harbor's live ISO."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

TARGET=Path('/mnt/harbor-install-target')
SOURCE=Path('/run/live/medium/live/filesystem.squashfs')


def run(*args, capture=False):
    result=subprocess.run(args,check=True,text=True,stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ''


def nodes(disk):
    yield disk
    for child in disk.get('children',[]):
        yield from nodes(child)


def inventory():
    tree=json.loads(run('lsblk','-J','-b','-p','-o','NAME,PATH,SIZE,TYPE,MOUNTPOINTS,MODEL,SERIAL,WWN,RO',capture=True))['blockdevices']
    links={}
    for link in sorted(Path('/dev/disk/by-id').glob('*'),key=lambda p:(not p.name.startswith('wwn-'),p.name)):
        if not re.search(r'-part\d+$',link.name):
            links.setdefault(str(link.resolve()),str(link))
    result=[]
    for disk in tree:
        if disk.get('type')!='disk' or disk.get('size',0)<16*1024**3 or disk.get('ro'):
            continue
        children=list(nodes(disk))
        if any(any(p for p in n.get('mountpoints') or []) for n in children):
            continue
        if any(any((Path('/sys/class/block')/Path(n['path']).name/'holders').glob('*')) for n in children):
            continue
        if disk['path'] not in links:
            continue
        result.append(dict(disk,id=links[disk['path']]))
    return result


def fingerprint(disk):
    return hashlib.sha256(json.dumps({k:disk.get(k) for k in ('id','path','size','serial','wwn')},sort_keys=True).encode()).hexdigest()


def install(disk):
    if 'harbour.recovery=1' in Path('/proc/cmdline').read_text().split():
        source_type=run('findmnt','-n','-T',str(SOURCE),'-o','FSTYPE',capture=True)
        if source_type!='tmpfs':
            raise RuntimeError('Recovery installation requires the complete source image in RAM. No disk was erased.')
    selected=fingerprint(disk)
    current=next((d for d in inventory() if d['id']==disk['id']),None)
    if not current or fingerprint(current)!=selected:
        raise RuntimeError('Disk identity or eligibility changed. Nothing was erased.')
    if TARGET.exists() and os.path.ismount(TARGET):
        raise RuntimeError('The installation mount is already in use.')
    device=current['id']
    run('wipefs','--all',device)
    run('parted','-s',device,'mklabel','gpt','mkpart','BIOS','1MiB','3MiB','set','1','bios_grub','on',
        'mkpart','ESP','fat32','3MiB','515MiB','set','2','esp','on','mkpart','harbor-root','ext4','515MiB','100%')
    run('partprobe',device)
    run('udevadm','settle')
    # Resolve new partitions through the same stable device ID, never guessed letters.
    efi=Path(device+'-part2');root=Path(device+'-part3')
    if not efi.exists() or not root.exists():
        raise RuntimeError('The new partitions did not appear. Stop and check the disk.')
    run('mkfs.vfat','-F','32','-n','HARBOR_EFI',str(efi))
    run('mkfs.ext4','-F','-L','harbor-root',str(root))
    TARGET.mkdir(parents=True,exist_ok=True)
    mounted=[]
    try:
        run('mount',str(root),str(TARGET));mounted.append(TARGET)
        run('unsquashfs','-f','-processors','2','-d',str(TARGET),str(SOURCE))
        # Fresh identities and administrator setup; no live-session credentials survive.
        for pattern in ('etc/ssh/ssh_host_*','var/lib/harbor/tls.*','var/lib/harbor/admin.json',
                        'var/lib/harbor/setup-token','var/lib/harbor/events.json','var/lib/harbor/config.json',
                        'etc/systemd/system/getty@tty1.service.d/harbor-live.conf',
                        'etc/systemd/system/getty@tty2.service.d/harbor-live.conf',
                        'etc/systemd/system/serial-getty@ttyS0.service.d/harbor-live.conf','root/.bash_profile'):
            for path in TARGET.glob(pattern):
                if not path.is_relative_to(TARGET):
                    raise RuntimeError('Invalid cleanup target.')
                path.unlink(missing_ok=True)
        (TARGET/'etc/machine-id').write_text('')
        (TARGET/'var/lib/dbus/machine-id').unlink(missing_ok=True)
        conf=TARGET/'etc/harbor.conf'
        conf.write_text('\n'.join(line for line in conf.read_text().splitlines() if not line.startswith('HARBOR_LIVE='))+'\n')
        (TARGET/'etc/hostname').write_text('harbor\n')
        root_uuid=run('blkid','-s','UUID','-o','value',str(root),capture=True)
        efi_uuid=run('blkid','-s','UUID','-o','value',str(efi),capture=True)
        if not re.fullmatch(r'[0-9a-f-]{36}',root_uuid) or not re.fullmatch(r'[0-9A-Fa-f-]{9}',efi_uuid):
            raise RuntimeError('Filesystem identities could not be verified.')
        (TARGET/'etc/fstab').write_text(f'UUID={root_uuid} / ext4 defaults 0 1\nUUID={efi_uuid} /boot/efi vfat umask=0077 0 2\n')
        (TARGET/'boot/efi').mkdir(parents=True,exist_ok=True)
        run('mount',str(efi),str(TARGET/'boot/efi'));mounted.append(TARGET/'boot/efi')
        run('grub-install','--target=x86_64-efi','--efi-directory='+str(TARGET/'boot/efi'),
            '--boot-directory='+str(TARGET/'boot'),'--removable','--no-nvram')
        run('grub-install','--target=i386-pc','--boot-directory='+str(TARGET/'boot'),device)
        (TARGET/'boot/grub/grub.cfg').write_text(f'''set timeout=5
set default=0
menuentry 'Harbour OS 0.10.2' {{
  search --no-floppy --fs-uuid --set=root {root_uuid}
  linux /boot/harbor-vmlinuz root=UUID={root_uuid} rw rootwait quiet splash console=tty0 console=ttyS0,115200n8 panic=30
  initrd /boot/harbor-initrd
}}
''')
        (TARGET/'var/lib/harbor/installation.json').write_text(json.dumps({'version':'0.10.2','target':current['id'],
            'serial':current.get('serial'),'root_uuid':root_uuid,'installer':'Harbor live ISO'},indent=2))
        run('sync','-f',str(TARGET))
    finally:
        for mount in reversed(mounted):
            run('umount',str(mount))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--disk',help='Preselect a stable device ID; confirmation is still required.')
    args=parser.parse_args()
    if os.geteuid()!=0 or 'boot=live' not in Path('/proc/cmdline').read_text().split() or not SOURCE.is_file():
        raise SystemExit('Run this installer from the booted Harbor live ISO.')
    disks=inventory()
    print('\nHARBOUR OS 0.10.2 — INSTALL TO DISK\n')
    print('The destination disk will be completely erased. Other disks are left untouched.')
    print('The live USB, mounted disks, and disks smaller than 16 GiB are excluded.\n')
    for i,disk in enumerate(disks,1):
        print(f"{i}. {disk.get('model','')} | {disk['size']/1024**3:.1f} GiB | serial {disk.get('serial') or '(none)'}\n   {disk['id']}")
    if not disks:
        raise SystemExit('No eligible destination disk. Shut down and connect a disk of at least 16 GiB.')
    if args.disk:
        disk=next((d for d in disks if d['id']==args.disk),None)
        if not disk:
            raise SystemExit('The specified disk is unavailable or protected.')
    else:
        answer=input('\nDestination number (Enter cancels): ').strip()
        if not answer:
            return
        if not answer.isdecimal() or not 1<=int(answer)<=len(disks):
            raise SystemExit('Invalid destination.')
        disk=disks[int(answer)-1]
    confirmation='ERASE '+str(disk.get('serial') or Path(disk['id']).name)
    print(f"\nDESTINATION: {disk['id']}\nMODEL: {disk.get('model','')}\nSERIAL: {disk.get('serial','')}\nCAPACITY: {disk['size']/1024**3:.1f} GiB")
    print('All partitions and files on this disk will be permanently erased.')
    if input('Type '+confirmation+' to install: ').strip()!=confirmation:
        raise SystemExit('Cancelled. Nothing was erased.')
    install(disk)
    print('\nINSTALLATION COMPLETE. Shut down, remove the USB, and boot the installed disk.')
    print('The graphical first-boot screen will help you create your account. No setup code is needed.')
    print('Then open Storage → Create storage to configure your separate data disks.')


if __name__=='__main__':
    try:
        main()
    except (RuntimeError,subprocess.CalledProcessError,KeyboardInterrupt) as error:
        print('\nInstallation stopped:',error,file=sys.stderr)
        sys.exit(1)
