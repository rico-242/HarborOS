"""Small owner-only VM control layer over the host libvirt API."""
import re, subprocess, xml.etree.ElementTree as ET
from pathlib import Path
import os
import shutil

NAME=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$')
ISO_ROOT=Path('/var/lib/libvirt/boot/harbour')
DISK_ROOT=Path('/var/lib/libvirt/images/harbour')
class VirtualMachines:
    def __init__(self, app, error): self.app,self.error=app,error
    def _run(self,*args,check=True):
        result=subprocess.run(['virsh','-c','qemu:///system',*args],capture_output=True,text=True,timeout=60,check=False)
        if check and getattr(result,'returncode',0):raise self.error(result.stderr.strip() or 'The hypervisor could not complete this action.')
        return result
    def info(self):
        try: out=self._run('list','--all').stdout
        except Exception as e: return {'ready':False,'error':str(e),'vms':[]}
        rows=[]
        for line in out.splitlines()[2:]:
            m=re.match(r'\s*(\d+|-)\s+([^\s]+)\s+(.+?)\s*$',line)
            if m: rows.append({'id':m.group(1),'name':m.group(2),'state':m.group(3)})
        return {'ready':True,'vms':rows,'isos':self.isos()}
    def console_address(self,name):
        if not NAME.fullmatch(name):raise self.error('Invalid VM name.')
        root=ET.fromstring(self._run('dumpxml',name).stdout)
        graphics=root.find("./devices/graphics[@type='vnc']")
        if graphics is None:raise self.error('This VM has no VNC display.',409)
        host=graphics.get('listen') or (graphics.find('listen').get('address') if graphics.find('listen') is not None else '')
        port=int(graphics.get('port','-1'))
        if host!='127.0.0.1' or not 5900<=port<=65535:raise self.error('Start the VM to open its local console.',409)
        return (host,port)
    def isos(self):
        root=ISO_ROOT
        return [p.name for p in sorted(root.glob('*.iso')) if p.is_file() and not p.is_symlink()]
    def create(self,data):
        name=str(data.get('name',''))
        if not NAME.fullmatch(name):raise self.error('Use letters, numbers, hyphens or underscores for the VM name.')
        try:cpu=int(data.get('cpu',2));memory=int(data.get('memory',2048));disk=int(data.get('disk',32))
        except (TypeError,ValueError):raise self.error('CPU, memory and disk must be whole numbers.')
        if not 1<=cpu<=min(64,os.cpu_count() or 1) or not 512<=memory<=262144 or not 8<=disk<=2048:raise self.error('Choose valid CPU, memory and disk sizes.')
        iso=str(data.get('iso',''))
        if iso not in self.isos():raise self.error('Choose an ISO from the ISO library.')
        network=str(data.get('network','default'))
        if network!='default':raise self.error('Choose the default NAT network.')
        memory_info=Path('/proc/meminfo')
        if memory_info.exists():
            available=int(re.search(r'MemAvailable:\s+(\d+)',memory_info.read_text()).group(1))//1024
            if memory>max(512,available-512):raise self.error('There is not enough free memory. Reduce the VM memory size.')
        def execute():
            root=DISK_ROOT;root.mkdir(parents=True,exist_ok=True);root.chmod(0o755)
            path=root/(name+'.qcow2')
            if path.exists() or self._run('dominfo',name,check=False).returncode==0:raise self.error('A VM or disk with this name already exists.')
            if shutil.disk_usage(root).free<(disk+2)*1024**3:raise self.error('There is not enough space on the system SSD for this disk.')
            self.app.job_progress('Preparing network','Starting the private NAT network.')
            self._run('net-start','default',check=False)
            self._run('net-autostart','default')
            self.app.job_progress('Creating virtual machine','Allocating its disk and starting the installer.')
            result=subprocess.run(['virt-install','--connect','qemu:///system','--name',name,'--memory',str(memory),'--vcpus',str(cpu),'--disk',f'path={path},size={disk},format=qcow2','--cdrom',str(ISO_ROOT/iso),'--network','network=default,model=virtio','--graphics','vnc,listen=127.0.0.1','--osinfo','generic','--noautoconsole'],capture_output=True,text=True,timeout=180)
            if result.returncode:raise self.error(result.stderr[-3000:] or 'The hypervisor could not create the VM.')
            xml=ET.fromstring(self._run('dumpxml',name,'--inactive').stdout)
            reboot=xml.find('on_reboot')
            if reboot is not None:reboot.text='restart'
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w',suffix='.xml') as stream:
                stream.write(ET.tostring(xml,encoding='unicode'));stream.flush();self._run('define',stream.name)
            return {'name':name}
        return self.app.job('Create virtual machine',execute,kind='system',target=name)
    def action(self,data):
        name=str(data.get('name',''))
        if not NAME.fullmatch(name): raise self.error('Use a simple VM name with letters, numbers, hyphens, or underscores.')
        action=data.get('action')
        if action=='start': self._run('start',name)
        elif action=='shutdown': self._run('shutdown',name)
        elif action=='destroy':
            if data.get('confirmation')!='STOP '+name:raise self.error('Type STOP '+name+' to force power off.')
            self._run('destroy',name)
        elif action=='reboot':self._run('reboot',name)
        elif action in ('eject','boot-disk','boot-iso'):
            xml=ET.fromstring(self._run('dumpxml',name,'--inactive').stdout)
            if action=='eject':
                for cd in xml.findall("./devices/disk[@device='cdrom']"):
                    if cd.find('source') is None:continue
                    target=cd.find('target').get('dev')
                    self._run('change-media',name,target,'--eject','--config')
                    if self._run('domstate',name).stdout.strip()=='running':self._run('change-media',name,target,'--eject','--live')
            else:
                node=xml.find('os')
                reboot=xml.find('on_reboot')
                if reboot is not None:reboot.text='restart'
                for boot in list(node.findall('boot')):node.remove(boot)
                for disk_node in xml.findall('./devices/disk'):
                    for boot in list(disk_node.findall('boot')):disk_node.remove(boot)
                for dev in (('hd','cdrom') if action=='boot-disk' else ('cdrom','hd')):ET.SubElement(node,'boot',dev=dev)
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w',suffix='.xml') as stream:
                    stream.write(ET.tostring(xml,encoding='unicode'));stream.flush();self._run('define',stream.name)
        elif action=='delete':
            if data.get('confirmation')!='DELETE '+name: raise self.error('Type DELETE '+name+' to confirm.')
            self._run('destroy',name,check=False); self._run('undefine',name,'--nvram')
        elif action=='snapshot': self._run('snapshot-create-as',name,str(data.get('snapshot','snapshot')))
        else: raise self.error('Unknown VM action.')
        return self.info()
