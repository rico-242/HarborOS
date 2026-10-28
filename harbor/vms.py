"""Small owner-only VM control layer over the host libvirt API."""
import re, subprocess, xml.etree.ElementTree as ET

NAME=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$')
class VirtualMachines:
    def __init__(self, app, error): self.app,self.error=app,error
    def _run(self,*args,check=True): return subprocess.run(['virsh','-c','qemu:///system',*args],capture_output=True,text=True,timeout=60,check=check)
    def info(self):
        try: out=self._run('list','--all').stdout
        except Exception as e: return {'ready':False,'error':str(e),'vms':[]}
        rows=[]
        for line in out.splitlines()[2:]:
            m=re.match(r'\s*(\d+)?\s+([^\s]+)\s+(.+?)\s*$',line)
            if m: rows.append({'id':m.group(1),'name':m.group(2),'state':m.group(3)})
        return {'ready':True,'vms':rows}
    def action(self,data):
        name=str(data.get('name',''))
        if not NAME.fullmatch(name): raise self.error('Use a simple VM name with letters, numbers, hyphens, or underscores.')
        action=data.get('action')
        if action=='start': self._run('start',name)
        elif action=='shutdown': self._run('shutdown',name)
        elif action=='destroy': self._run('destroy',name)
        elif action=='delete':
            if data.get('confirmation')!='DELETE '+name: raise self.error('Type DELETE '+name+' to confirm.')
            self._run('destroy',name,check=False); self._run('undefine',name,'--nvram',check=False)
        elif action=='snapshot': self._run('snapshot-create-as',name,str(data.get('snapshot','snapshot')))
        else: raise self.error('Unknown VM action.')
        return self.info()
