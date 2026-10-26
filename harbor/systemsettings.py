"""Owner-only system settings, package checks and independent update jobs."""
import json
from pathlib import Path
import platform
import re
import secrets
import socket
from zoneinfo import available_timezones


class SystemSettings:
    def __init__(self,app,run,error,atomic):
        self.app,self.run,self.error,self.atomic=app,run,error,atomic
        self.update_file=app.state/'system-update.json'
        self.check_file=app.state/'package-check.json'

    def external_status(self):
        if hasattr(self.app,'networking'):self.app.networking.status()
        if hasattr(self.app,'releases'):self.app.releases.status()
        if self.update_file.exists():
            try:
                value=json.loads(self.update_file.read_text())
                if re.fullmatch(r'[a-f0-9]{16}',value.get('id','')):self.app.jobs[value['id']]=value
            except (OSError,ValueError):pass

    def info(self):
        network=[];services={};zone='Etc/UTC'
        try:zone=str(Path('/etc/localtime').resolve().relative_to('/usr/share/zoneinfo'))
        except ValueError:pass
        if not self.app.demo:
            response=self.run('ip','-j','address','show',check=False)
            if response.returncode==0:network=json.loads(response.stdout)
            for name in ('harbor','smbd','docker','ssh','lightdm'):
                services[name]=self.run('systemctl','is-active',name,check=False).stdout.strip()
        updates=json.loads(self.check_file.read_text()) if self.check_file.exists() else {'checked':None,'packages':[]}
        self.external_status()
        return {'hostname':socket.gethostname(),'timezone':zone,'timezones':sorted(available_timezones() or {'Etc/UTC'}),
                'network':network,'services':services,'kernel':platform.release(),'updates':updates,
                'update':json.loads(self.update_file.read_text()) if self.update_file.exists() else None}

    def action(self,data):
        action=data.get('action')
        if self.app.demo:raise self.error('System changes are available on the Harbour appliance.',409)
        if action=='timezone':
            zone=data.get('timezone')
            if zone not in available_timezones():raise self.error('Choose a supported timezone.')
            self.run('timedatectl','set-timezone',zone)
            self.app.event('Changed timezone to '+zone+'.');return {'ok':True}
        if action in ('reboot','poweroff'):
            if data.get('confirmation')!=socket.gethostname():raise self.error('Confirm using the server hostname.')
            self.external_status()
            if any(j['state'] in ('queued','running') for j in self.app.jobs.values()):raise self.error('Wait for the current system job to finish.',409)
            self.run('systemd-run','--collect','--on-active=3','--unit=harbour-power','/usr/bin/systemctl',action)
            self.app.event('Scheduled '+action+'.');return {'scheduled':True}
        if action=='check-updates':
            def check():
                self.run('apt-get','update',timeout=300)
                result=self.run('apt-get','--simulate','upgrade',timeout=90)
                packages=[]
                for line in result.stdout.splitlines():
                    if line.startswith('Inst '):
                        parts=line.split();packages.append({'name':parts[1],'detail':' '.join(parts[2:])})
                from datetime import datetime,timezone
                value={'checked':datetime.now(timezone.utc).isoformat(),'packages':packages}
                self.atomic(self.check_file,value);return value
            return self.app.job('Check system packages',check)
        if action=='install-updates':
            if data.get('confirmation')!='UPDATE':raise self.error('Confirm installation of signed Debian system updates.')
            with self.app.lock:
                self.external_status()
                if any(j['state'] in ('queued','running') for j in self.app.jobs.values()):raise self.error('Wait for the current system job to finish.',409)
                ident=secrets.token_hex(8)
                value={'id':ident,'title':'Install system package updates','state':'queued','actor':self.app.admin['username'],'external':True}
                self.atomic(self.update_file,value)
                try:self.run('systemd-run','--collect','--unit=harbour-system-update','/usr/local/sbin/harbour-package-update',ident)
                except Exception:
                    value['state']='failed';self.atomic(self.update_file,value);raise
                self.app.jobs[ident]=value;return value
        raise self.error('Unknown system setting.')
