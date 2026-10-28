#!/usr/bin/env python3
"""Harbor OS control service. Python standard library; Linux appliance backend."""
from __future__ import annotations

import base64
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import hmac
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import zipfile
from urllib.parse import parse_qs, unquote, urlsplit

VERSION = '0.14.0'
WEB = Path(__file__).parent / 'web'
sys.path.insert(0, str(Path(__file__).parent))
from appstore import CATALOG_INFO, OFFICIAL, prepare as prepare_app, public_item, project_name, compose_app_state, provision_app_mounts
from storage import StorageManager, LEVELS
from fileops import FileOperations,filename,transfer
from members import Members
from systemsettings import SystemSettings
from virtualization import Virtualization
from vms import VirtualMachines
from networking import Networking
from releases import Releases
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$')
USERNAME = re.compile(r'^[a-z_][a-z0-9_-]{0,31}$')
MAX_UPLOAD = 1024 * 1024 * 1024
CATALOG = {
    'jellyfin': {'name': 'Jellyfin', 'description': 'Your movies, music, and shows. Stream from your own server.',
                 'image': 'jellyfin/jellyfin:latest', 'port': 8096, 'container_port': 8096,
                 'color': '#ad91ff', 'letter': 'J', 'category': 'Media'},
    'syncthing': {'name': 'Syncthing', 'description': 'Keep folders in sync between your own devices.',
                  'image': 'syncthing/syncthing:latest', 'port': 8384, 'container_port': 8384,
                  'color': '#78ccff', 'letter': 'S', 'category': 'Files'},
}


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def run(*args, timeout=30, check=True, input_text=None):
    """Execute fixed argv arrays, never a shell or browser-supplied command."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, input=input_text)
    except FileNotFoundError:
        raise APIError(f'{args[0]} is not installed on this system.', 503)
    except subprocess.TimeoutExpired:
        raise APIError(f'{args[0]} did not finish in time. Check the activity log.', 504)
    if check and result.returncode:
        raise APIError((result.stderr.strip() or result.stdout.strip() or f'{args[0]} failed')[-1800:], 409)
    return result


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def password_record(username, password):
    if not USERNAME.fullmatch(username):
        raise APIError('Use a lowercase administrator name with letters, numbers, or underscores.')
    if not isinstance(password, str) or not 12 <= len(password) <= 256 or any(c in password for c in '\r\n\x00'):
        raise APIError('Use a password between 12 and 256 characters.')
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return {'username': username, 'salt': salt, 'hash': digest}


def verify_password(record, password):
    if not isinstance(password, str) or len(password) > 256:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(record['salt']), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(digest, record['hash'])


def valid_name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise APIError('Use 1–48 letters, numbers, hyphens, or underscores, starting with a letter or number.')
    return value


def contained_path(root, relative=''):
    root = Path(root).resolve()
    if not isinstance(relative, str) or '\x00' in relative or '\\' in relative:
        raise APIError('Invalid file path.')
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise APIError('This path is outside your storage.', 403)
    return candidate


class Harbor:
    def __init__(self, state=None, storage=None, apps=None, demo=False):
        self.demo = demo
        self.state = Path(state or os.getenv('HARBOR_STATE', '/var/lib/harbor'))
        self.storage = Path(storage or os.getenv('HARBOR_STORAGE', '/srv/harbor/storage'))
        self.apps = Path(apps or os.getenv('HARBOR_APPS', '/srv/harbor/apps'))
        for path in (self.state, self.storage, self.apps):
            path.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.sessions = {}
        self.attempts = defaultdict(deque)
        self.jobs = {}
        self.job_context=threading.local()
        self.pool = ThreadPoolExecutor(max_workers=2)
        from systemfiles import SystemFiles
        self.system_files=SystemFiles(self,self.state/'system-files' if demo else Path('/srv/harbor/system-data'),contained_path,APIError,atomic_json)
        self.config_path = self.state / 'config.json'
        self.config = json.loads(self.config_path.read_text()) if self.config_path.exists() else {'shares': [], 'apps': []}
        self.admin_path = self.state / 'admin.json'
        self.admin = json.loads(self.admin_path.read_text()) if self.admin_path.exists() else None
        self.setup_path = self.state / 'setup-token'
        self.setup_path.unlink(missing_ok=True)
        self.setup_sessions = {}
        self.events_path = self.state / 'events.json'
        self.events = json.loads(self.events_path.read_text()) if self.events_path.exists() else []
        self.previous_cpu = None
        self.previous_network = None
        self.storage_manager = StorageManager(self,run,APIError)
        self.file_operations = FileOperations(self,contained_path,APIError,atomic_json)
        self.members = Members(self,run,APIError,password_record,atomic_json)
        self.system_settings=SystemSettings(self,run,APIError,atomic_json)
        self.virtualization=Virtualization(self,run,APIError)
        self.virtual_machines=VirtualMachines(self,APIError)
        self.networking=Networking(self,run,APIError,atomic_json)
        self.releases=Releases(self,run,APIError,atomic_json,VERSION)
        from recovery import Recovery
        self.recovery=Recovery(self,run,APIError,VERSION)
        from appsettings import AppSettings
        from externaldrives import ExternalDrives
        self.app_settings=AppSettings(self,run,APIError,atomic_json)
        self.external_drives=ExternalDrives(self,run,APIError)
        self.archive_slots=threading.BoundedSemaphore(2)
        if self.demo:
            (self.storage / 'shares').mkdir(exist_ok=True)
            (self.storage / 'shares' / 'Welcome').mkdir(exist_ok=True)
            welcome = self.storage / 'shares' / 'Welcome' / 'Read me.txt'
            if not welcome.exists():
                welcome.write_text('Welcome to Harbor OS. This is a local development preview.\n')

    def save(self):
        atomic_json(self.config_path, self.config)

    def event(self, message, level='info'):
        with self.lock:
            self.events.insert(0, {'time': datetime.now(timezone.utc).isoformat(), 'message': message, 'level': level})
            self.events = self.events[:100]
            atomic_json(self.events_path, self.events)

    def login(self, username, password, address):
        now = time.monotonic()
        with self.lock:
            attempts = self.attempts[address]
            while attempts and attempts[0] < now - 300:
                attempts.popleft()
            if len(attempts) >= 8:
                raise APIError('Too many attempts. Wait five minutes and try again.', 429)
            attempts.append(now)
            # Hash a dummy record too, reducing username timing differences.
            record = self.admin if self.admin and self.admin['username']==username else next((r for r in self.members.records if r['username']==username and r.get('enabled',True)),None)
            record = record or {'salt': '00' * 16, 'hash': '00' * 64, 'username': ''}
            valid = verify_password(record, password)
            if not valid or not hmac.compare_digest(str(username), record['username']):
                raise APIError('The username or password is incorrect.', 401)
            attempts.clear()
            # Bound memory use and enforce expiration even for abandoned sessions.
            self.sessions = {key: val for key, val in self.sessions.items() if val['expires'] > now}
            if len(self.sessions) >= 64:
                self.sessions.pop(next(iter(self.sessions)))
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.sessions[token] = {'username': record['username'], 'role':'owner' if self.admin and record['username']==self.admin['username'] else 'member','csrf': csrf, 'expires': now + 8 * 3600}
            return token, self.sessions[token]

    def setup(self, data, address, local_authorized=False):
        with self.lock:
            if self.admin:
                raise APIError('This server already has an administrator.', 409)
            if not local_authorized:
                raise APIError('Create the first account on this computer’s graphical setup screen.',403)
            if data.get('confirm',data.get('password'))!=data.get('password'):
                raise APIError('The passwords do not match.')
            record = password_record(data.get('username', ''), data.get('password', ''))
            if not self.demo:
                import pwd
                try:
                    pwd.getpwnam(record['username'])
                except KeyError:
                    pass
                else:
                    raise APIError('That Linux account already exists. Choose a new administrator name.', 409)
                homes = Path('/srv/harbor/users')
                homes.mkdir(parents=True, exist_ok=True)
                homes.chmod(0o755)
                try:
                    run('useradd', '-m', '-d', str(homes / record['username']), '-s', '/bin/bash', '-G', 'sudo', record['username'])
                    run('chpasswd', input_text=record['username'] + ':' + data['password'] + '\n')
                    run('smbpasswd', '-s', '-a', record['username'], input_text=data['password'] + '\n' + data['password'] + '\n')
                except Exception:
                    run('userdel', record['username'], check=False)
                    raise
            self.admin = record
            atomic_json(self.admin_path, self.admin)
            self.setup_sessions.clear()
            self.config['onboarding_complete']=False
            self.save()
            self.event('Administrator setup completed.')
            return self.login(self.admin['username'], data['password'], address)

    def storage_info(self):
        usage = shutil.disk_usage(self.storage)
        info = {'total': usage.total, 'used': usage.used, 'free': usage.free, 'filesystem': 'development',
                'source': str(self.storage), 'mounted': self.demo, 'redundancy': 'Not assessed'}
        if not self.demo:
            result = run('findmnt', '-J', '-T', str(self.storage), '-o', 'SOURCE,FSTYPE,TARGET', check=False)
            if result.returncode == 0:
                fs = json.loads(result.stdout)['filesystems'][0]
                info.update(filesystem=fs['fstype'], source=fs['source'], mounted=fs['target'] == str(self.storage))
                if fs['source'].startswith('/dev/md'):
                    detail = run('mdadm', '--detail', '--export', fs['source'], check=False)
                    values = dict(line.split('=', 1) for line in detail.stdout.splitlines() if '=' in line)
                    info['redundancy'] = values.get('MD_LEVEL', 'MD RAID')
                    info['raid_state'] = values.get('MD_STATE', 'Unknown')
                elif fs['fstype'] == 'btrfs':
                    details = run('btrfs', 'filesystem', 'usage', '-b', str(self.storage), timeout=10, check=False).stdout
                    profile = re.search(r'^Data,([^:]+):', details, re.MULTILINE)
                    info['redundancy'] = ('Mirrored (RAID1)' if profile and profile[1] == 'RAID1' else profile[1] if profile else 'Not assessed')
                source=fs['source'].split('[')[0]
                base=Path(source).resolve().name
                md=Path('/sys/class/block')/base/'md'
                if md.is_dir():
                    for field in ('level','array_state','degraded','sync_action','sync_completed'):
                        try:
                            info[field]=(md/field).read_text().strip()
                        except OSError:
                            pass
                    info['redundancy']=info.get('level','MD RAID').upper()
                    info['healthy']=info.get('degraded','0')=='0' and info.get('array_state') not in ('inactive','clear')
                else:
                    info['healthy']=info['mounted']
                    if info['mounted'] and fs['fstype']=='btrfs':
                        members=run('btrfs','filesystem','show','--raw',str(self.storage),check=False)
                        if members.returncode or re.search(r'\bmissing\b',members.stdout,re.I):info['healthy']=False
        hybrid=self.storage_manager.hybrid_status()
        if hybrid:
            info.update(redundancy=hybrid['name'],healthy=bool(info['mounted']) and hybrid['healthy'],hybrid_arrays=hybrid['arrays'])
            syncing=[a for a in hybrid['arrays'] if a.get('sync_action','idle')!='idle']
            if syncing:info.update(sync_action='Synchronizing protected tiers',sync_completed='; '.join(a['path']+': '+a.get('sync_completed','') for a in syncing))
        if not self.demo:info.update(self.storage_manager.pool_health())
        info['storage_operation_pending']=self.storage_manager.recovery_pending()
        info['name']=self.config.get('storage',{}).get('name','Data volume')
        info['configured']=bool(self.config.get('storage',{}).get('uuid'))
        if info['mounted'] and self.config.get('storage',{}).get('level')=='linear':
            info['redundancy']='JBOD (Btrfs single)'
        return info

    def hardware_metrics(self):
        temperature = None
        network = {'interface': None, 'receive': None, 'transmit': None}
        try:
            for sensor in Path('/sys/class/hwmon').glob('hwmon*'):
                if (sensor / 'name').read_text().strip() == 'coretemp':
                    temperature = round(int((sensor / 'temp1_input').read_text()) / 1000, 1)
                    break
        except (OSError, ValueError):
            pass
        try:
            routes = Path('/proc/net/route').read_text().splitlines()[1:]
            interface = next(row.split()[0] for row in routes if row.split()[1] == '00000000')
            for row in Path('/proc/net/dev').read_text().splitlines()[2:]:
                name, values = row.split(':', 1)
                if name.strip() != interface:
                    continue
                counts = values.split()
                current = (time.monotonic(), interface, int(counts[0]), int(counts[8]))
                network['interface'] = interface
                with self.lock:
                    previous = self.previous_network
                    if previous and previous[1] == interface and current[0] - previous[0] >= 0.1:
                        elapsed = current[0] - previous[0]
                        network['receive'] = max(0, round((current[2] - previous[2]) / elapsed))
                        network['transmit'] = max(0, round((current[3] - previous[3]) / elapsed))
                    self.previous_network = current
                break
        except (OSError, ValueError, IndexError, StopIteration):
            pass
        return {'temperature': temperature, 'network': network}

    def summary(self):
        memory = {'total': 0, 'used': 0}
        uptime = 0
        cpu = 0
        if Path('/proc/meminfo').exists():
            mem = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()}
            memory = {'total': mem['MemTotal'], 'used': mem['MemTotal'] - mem['MemAvailable']}
            uptime = float(Path('/proc/uptime').read_text().split()[0])
            counters = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
            current = (sum(counters), counters[3] + counters[4])
            with self.lock:
                if self.previous_cpu and current[0] > self.previous_cpu[0]:
                    cpu = round(100 * (1 - (current[1] - self.previous_cpu[1]) / (current[0] - self.previous_cpu[0])), 1)
                self.previous_cpu = current
        alerts_path = self.state / 'hardware-alerts.json'
        alerts = json.loads(alerts_path.read_text()) if alerts_path.exists() else []
        return {'version': VERSION, 'hostname': socket.gethostname(), 'kernel': platform.release(), 'alerts': alerts,
                'platform': platform.machine(), 'demo': self.demo, 'cpu': cpu, 'cores': os.cpu_count(),
                'memory': memory, 'uptime': uptime, 'storage': self.storage_info(), 'shares': len(self.config['shares']),
                'installed_apps': len(self.config['apps']), 'events': self.events[:6], **self.hardware_metrics()}

    def disks(self):
        if self.demo:
            return []
        result = run('lsblk', '-J', '-b', '-o', 'NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL,ROTA')
        return json.loads(result.stdout)['blockdevices']

    def files(self, relative):
        path = contained_path(self.storage / 'shares', relative)
        if not path.is_dir():
            raise APIError('Folder not found.', 404)
        entries = []
        for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
            if child.is_symlink() or child.name.startswith('.harbour-upload-'):
                continue
            stat = child.stat()
            entries.append({'name': child.name, 'directory': child.is_dir(), 'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()})
            if len(entries) >= 2000:
                break
        return {'path': relative, 'entries': entries}

    def require_storage(self):
        if not self.demo and not self.storage_info()['mounted']:
            raise APIError('The data volume is not mounted. Storage writes are disabled to protect the boot filesystem.', 409)

    def access_path(self,relative,username,write=False,allow_root=False):
        path=contained_path(self.storage/'shares',relative)
        parts=path.relative_to((self.storage/'shares').resolve()).parts
        if any(p.startswith('.harbour-upload-') for p in parts):raise APIError('This upload is not complete.',403)
        if not parts:
            if allow_root and not write:return path
            raise APIError('Choose a shared folder.',400)
        share=next((s for s in self.config['shares'] if s['name']==parts[0]),None)
        if share is None or not self.members.allowed(share,username,write):
            raise APIError('You do not have access to this folder.',403)
        return path

    def owner(self, path):
        if not self.demo:
            import pwd
            try:
                user = pwd.getpwnam(self.admin['username'])
            except KeyError:
                raise APIError('The administrator needs a matching Linux account for SMB access.', 409)
            os.chown(path, user.pw_uid, user.pw_gid)
        path.chmod(0o2770 if path.is_dir() else 0o660)

    def create_share(self, name):
        name = valid_name(name)
        self.require_storage()
        with self.lock:
            if any(s['name'].casefold() == name.casefold() for s in self.config['shares']):
                raise APIError('A shared folder with that name already exists.', 409)
            root = self.storage / 'shares'
            root.mkdir(exist_ok=True)
            root.chmod(0o755)
            path = contained_path(root, name)
            if path.exists():
                raise APIError('A folder with that name already exists.', 409)
            if not self.demo and self.storage_info()['filesystem'] == 'btrfs':
                run('btrfs', 'subvolume', 'create', str(path))
            else:
                path.mkdir()
            self.owner(path)
            share = {'name': name, 'created': datetime.now(timezone.utc).isoformat()}
            self.config['shares'].append(share)
            self.save()
            try:
                self.sync_samba()
            except Exception:
                self.event(f'Folder {name} created, but SMB configuration failed; repair the sharing service.', 'error')
                raise
            self.event(f'Shared folder “{name}” created.')
            return share

    def sync_samba(self):
        if self.demo:
            return
        username = self.admin['username']
        if not USERNAME.fullmatch(username):
            raise APIError('Invalid SMB account.', 500)
        content = '# Managed by Harbor OS\n'
        for share in self.config['shares']:
            name = valid_name(share['name'])
            users=[r['username'] for r in self.members.public() if r['enabled'] and self.members.allowed(share,r['username'])]
            readers=[n for n in users if not self.members.allowed(share,n,True)]
            writers=[n for n in users if self.members.allowed(share,n,True)]
            content += f'\n[{name}]\n  path = {self.storage}/shares/{name}\n  valid users = {" ".join(users)}\n  force user = {username}\n  read only = yes\n  read list = {" ".join(readers)}\n  write list = {" ".join(writers)}\n  browseable = yes\n  create mask = 0660\n  directory mask = 2770\n'
        active=Path('/etc/samba/harbor-shares.conf');pending=active.with_suffix('.pending')
        previous=active.read_text() if active.exists() else ''
        pending.write_text(content)
        try:
            run('testparm','-s',str(pending),timeout=10)
            os.replace(pending,active)
            run('systemctl','reload','smbd',timeout=10)
        except Exception:
            active.write_text(previous);pending.unlink(missing_ok=True)
            run('systemctl','reload','smbd',timeout=10,check=False)
            raise

    def snapshot(self, name):
        name = valid_name(name)
        self.require_storage()
        if self.demo or self.storage_info()['filesystem'] != 'btrfs':
            raise APIError('Snapshots require a mounted Btrfs data volume.', 409)
        if not any(s['name'] == name for s in self.config['shares']):
            raise APIError('Shared folder not found.', 404)
        source = contained_path(self.storage / 'shares', name)
        target_root = self.storage / '.snapshots'
        target_root.mkdir(exist_ok=True)
        snapshot_id = name + '--' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(3)
        run('btrfs', 'subvolume', 'snapshot', '-r', str(source), str(target_root / snapshot_id))
        self.event(f'Snapshot created for “{name}”.')
        return {'id': snapshot_id}

    def snapshots(self):
        root = self.storage / '.snapshots'
        if not root.exists():
            return []
        return [{'id': p.name, 'share': p.name.split('--')[0],
                 'created': datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
                for p in sorted(root.iterdir(), reverse=True) if p.is_dir() and not p.is_symlink() and '--' in p.name]

    def restore(self, snapshot_id, name):
        self.require_storage()
        if self.demo or self.storage_info()['filesystem'] != 'btrfs':
            raise APIError('Restores require a mounted Btrfs data volume.', 409)
        name = valid_name(name)
        with self.lock:
            allowed = {s['id'] for s in self.snapshots()}
            if snapshot_id not in allowed:
                raise APIError('Snapshot not found.', 404)
            target = contained_path(self.storage / 'shares', name)
            if target.exists() or any(s['name'].casefold() == name.casefold() for s in self.config['shares']):
                raise APIError('Choose a new folder name for the restore.', 409)
            run('btrfs', 'subvolume', 'snapshot', str(self.storage / '.snapshots' / snapshot_id), str(target))
            self.owner(target)
            self.config['shares'].append({'name': name, 'created': datetime.now(timezone.utc).isoformat()})
            self.save()
            self.sync_samba()
            self.event(f'Snapshot restored into new folder “{name}”.')
            return {'name': name}

    def job(self, title, action,actor=None,kind='system',target=None):
        self.system_settings.external_status()
        with self.lock:
            if any(j['state'] in ('queued', 'running') for j in self.jobs.values()):
                raise APIError('Another system job is running. Let it finish first.', 409)
            ident = secrets.token_hex(8)
            value = {'id': ident, 'title': title, 'state': 'queued', 'kind':kind,'target':target,'created': datetime.now(timezone.utc).isoformat()}
            value['actor']=actor or (self.admin['username'] if self.admin else '')
            self.jobs[ident] = value
            # Retain a bounded number of completed jobs.
            while len(self.jobs) > 100:
                self.jobs.pop(next(iter(self.jobs)))
        def work():
            self.job_context.ident=ident
            value['state'] = 'running'
            value['started']=datetime.now(timezone.utc).isoformat()
            self.job_progress('Preparing', 'Checking the requested operation.')
            self.event(f'{title} started.')
            try:
                value['result'] = action()
                value['state'] = 'completed'
                value['finished']=datetime.now(timezone.utc).isoformat()
                self.job_progress('Complete', 'The operation finished successfully.')
                self.event(f'{title} completed.')
            except Exception as error:
                value.update(state='failed', error=str(error))
                value['finished']=datetime.now(timezone.utc).isoformat()
                self.event(f'{title} failed: {error}', 'error')
            finally:
                self.job_context.ident=None
        self.pool.submit(work)
        return dict(value)

    def job_progress(self, stage, detail=''):
        ident=getattr(getattr(self,'job_context',None),'ident',None)
        with self.lock:
            value=self.jobs.get(ident)
            if value is None:return
            step={'stage':stage,'detail':detail,'time':datetime.now(timezone.utc).isoformat()}
            value['stage']=stage;value['detail']=detail
            prior=value.get('steps',[])
            if prior and prior[-1]['stage']==stage:
                prior[-1]['detail']=detail
            else:prior=(prior+[step])[-30:]
            value['steps']=prior
            count=re.search(r'(\d+)\s*/\s*(\d+)',detail) if value.get('kind') in ('storage','recovery') else None
            percent=re.search(r'(\d+(?:\.\d+)?)%',detail) if value.get('kind') in ('storage','recovery') else None
            value['progress']=min(100,100*int(count[1])/int(count[2])) if count and int(count[2]) else min(100,float(percent[1])) if percent else None

    def app_list(self):
        containers = {}
        if not self.demo:
            result = run('docker', 'ps', '-a', '--format', '{{json .}}', timeout=10, check=False)
            if result.returncode:
                raise APIError('The app engine is unavailable. Check the Docker service.', 503)
            containers = {item['Names']: item for item in (json.loads(line) for line in result.stdout.splitlines())}
        result = []
        for ident, item in OFFICIAL.items():
            legacy = containers.get('harbor-' + ident)
            project = 'com.docker.compose.project=' + project_name(ident)
            group = [c for c in containers.values() if project in c.get('Labels','').split(',')]
            installed = bool(legacy or group or (self.state/'compose'/ident/'compose.json').exists())
            state = legacy['State'] if legacy else (compose_app_state(item,group) if installed else 'available')
            result.append(dict(public_item(item), installed=installed, state=state))
        return result

    def app_plan(self, ident, options=None):
        if ident not in OFFICIAL:
            raise APIError('Unknown application.')
        uid, gid = 1000, 1000
        if not self.demo and self.admin:
            import pwd
            account=pwd.getpwnam(self.admin['username'])
            uid,gid=account.pw_uid,account.pw_gid
        try:
            self.app_settings.system_location(True)
            media=self.storage if self.storage_info()['mounted'] else self.system_files.storage
            plan=prepare_app(ident,self.apps,media,uid,gid,options)
            plan['media_root']=str(media)
            plan['app_location']=str(self.apps/ident)
        except (ValueError, TypeError, KeyError) as error:
            raise APIError(str(error),409)
        return dict(plan, app=public_item(OFFICIAL[ident]), detail=OFFICIAL[ident].get('detail',''))

    def app_action(self, ident, action, options=None):
        if ident in OFFICIAL:
            if action not in ('install','start','stop','uninstall'):
                raise APIError('Unknown application action.')
            if self.demo or os.getenv('HARBOR_LIVE') == '1':
                raise APIError('Install Harbor on a disk before installing applications.',409)
            if action=='uninstall' and (not isinstance(options,dict) or options.get('confirmation')!='UNINSTALL '+ident):
                raise APIError('Type UNINSTALL '+ident+' to confirm. Application data will be kept.',409)
            plan=self.app_plan(ident,options) if action=='install' else None
            if plan and plan['warnings'] and not (options or {}).get('approve_access'):
                raise APIError('Review and approve the application access requirements.',409)
            def execute_compose():
                self.job_progress('Checking application', 'Checking the app configuration and existing containers.')
                legacy=run('docker','container','inspect','harbor-'+ident,check=False)
                if legacy.returncode==0:
                    if action=='install':
                        raise APIError('This application is already installed.',409)
                    self.job_progress('Starting application' if action=='start' else 'Stopping application', 'Updating the application containers.')
                    if action=='uninstall':
                        self.job_progress('Removing application', 'Stopping and removing the app container. Application data is kept.')
                        run('docker','rm','--force','harbor-'+ident,timeout=90)
                        previous=self.state/'compose'/ident/'compose.json'
                        if previous.exists():previous.replace(previous.with_name('compose.uninstalled.json'))
                        with self.lock:
                            self.config['apps']=[value for value in self.config['apps'] if value!=ident]
                            self.save()
                    else:
                        run('docker',action,'harbor-'+ident,timeout=90)
                    return {'app':ident,'action':action,'data_preserved':action=='uninstall'}
                folder=self.state/'compose'/ident
                config=folder/'compose.json'
                command=['docker-compose'] if shutil.which('docker-compose') else ['docker','compose']
                command+=['--project-name',project_name(ident),'--file',str(config)]
                if action=='install':
                    if config.exists():
                        raise APIError('This application is already configured. Use Start.',409)
                    self.app_settings.system_location(True)
                    folder.mkdir(parents=True,exist_ok=True)
                    provision_app_mounts(ident,plan['compose'],self.apps,Path(plan['media_root']))
                    atomic_json(config,plan['compose'])
                    try:
                        self.job_progress('Validating configuration', 'Checking the official app definition and your settings.')
                        run(*command,'config','--quiet',timeout=30)
                        self.job_progress('Downloading images', 'Downloading and extracting container images. Large apps can take several minutes.')
                        run(*command,'pull',timeout=1800)
                        self.job_progress('Starting containers', 'Creating the application containers and connecting their storage.')
                        run(*command,'up','-d','--remove-orphans',timeout=300)
                    except Exception:
                        self.job_progress('Cleaning up', 'Removing incomplete containers after the installation stopped.')
                        run(*command,'down',timeout=90,check=False)
                        config.unlink(missing_ok=True)
                        raise
                    with self.lock:
                        if ident not in self.config['apps']:
                            self.config['apps'].append(ident)
                            self.save()
                elif action=='uninstall':
                    if not config.exists():
                        raise APIError('This application has not been installed.',409)
                    self.job_progress('Removing application', 'Stopping and removing app containers and their network. Files, volumes and images are kept.')
                    run(*command,'down',timeout=180)
                    self.job_progress('Keeping application data', 'Retaining app files, named volumes and the previous container configuration for reinstallation.')
                    config.replace(folder/'compose.uninstalled.json')
                    with self.lock:
                        self.config['apps']=[value for value in self.config['apps'] if value!=ident]
                        self.save()
                else:
                    if not config.exists():
                        raise APIError('This application has not been installed.',409)
                    if action=='start' and ident=='anythingllm':
                        provision_app_mounts(ident,json.loads(config.read_text()),self.apps,self.storage)
                    self.job_progress('Starting containers' if action=='start' else 'Stopping containers', 'Applying the requested application state.')
                    run(*command,*(('up','-d') if action=='start' else ('stop',)),timeout=180)
                return {'app':ident,'action':action,'data_preserved':action=='uninstall'}
            return self.job(f'{action.title()} {OFFICIAL[ident]["name"]}',execute_compose,kind='app',target=ident)
        if ident not in CATALOG or action not in ('install', 'start', 'stop'):
            raise APIError('Unknown application or action.')
        if self.demo:
            raise APIError('Application installation is available on the Harbor OS appliance.', 409)
        spec = CATALOG[ident]
        def execute():
            container = 'harbor-' + ident
            if action == 'install':
                existing = run('docker', 'container', 'inspect', container, check=False)
                if existing.returncode == 0:
                    raise APIError('This application is already installed.', 409)
                run('docker', 'pull', spec['image'], timeout=900)
                data = contained_path(self.apps, ident)
                data.mkdir(exist_ok=True)
                args = ['docker', 'run', '-d', '--name', container, '--restart', 'unless-stopped',
                        '--cap-drop=ALL', '--security-opt=no-new-privileges:true', '--memory=2g', '--cpus=2',
                        '-p', f"{spec['port']}:{spec['container_port']}"]
                if ident == 'jellyfin':
                    args += ['-v', f'{data}:/config', '-v', f'{self.storage}/shares:/media:ro']
                else:
                    os.chown(data, 1000, 1000)
                    args += ['--user', '1000:1000', '-e', 'STGUIADDRESS=0.0.0.0:8384', '-v', f'{data}:/var/syncthing', '-p', '22000:22000/tcp', '-p', '22000:22000/udp', '-p', '21027:21027/udp']
                args.append(spec['image'])
                run(*args, timeout=60)
                with self.lock:
                    if ident not in self.config['apps']:
                        self.config['apps'].append(ident)
                        self.save()
            else:
                run('docker', action, container, timeout=60)
            return {'app': ident, 'action': action}
        return self.job(f'{action.title()} {spec["name"]}', execute)


class Handler(BaseHTTPRequestHandler):
    server_version = 'Harbor'
    sys_version = ''

    def require_local_console(self):
        if not self.server.local_console or self.client_address[0] not in ('127.0.0.1','::1'):
            raise APIError('Use the graphical screen connected to this computer to create its first account.',403)

    def console_host(self):
        if self.server.local_console:
            allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}',f'[::1]:{self.server.server_port}'}
            if self.headers.get('Host','') not in allowed:
                raise APIError('Invalid local-console host.',403)

    @property
    def app(self):
        return getattr(self,'_file_app',None) or self.server.app

    def file_volume(self,route,query,session):
        volume=query.get('volume',['pool'])[0]
        if volume not in ('pool','system'):raise APIError('Unknown file volume.')
        if volume=='system':
            if session['role']!='owner':raise APIError('System SSD files are available only to the owner.',403)
            allowed={'/api/files','/api/upload','/api/folders','/api/file-action','/api/trash','/api/trash-restore','/api/download','/api/archive','/api/image','/api/preview'}
            if route not in allowed:raise APIError('This endpoint does not support a system-file namespace.')
            self._file_app=self.server.app.system_files


    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, fmt, *args):
        # Do not log query strings, credentials, request bodies, or cookies.
        print(f'{self.client_address[0]} {self.command} {urlsplit(self.path).path}', flush=True)

    def headers_common(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Cache-Control', 'no-store')
        if self.server.tls:
            self.send_header('Strict-Transport-Security', 'max-age=86400')

    def reply(self, data, status=200, cookie=None):
        encoded = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.headers_common()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(encoded)

    def session(self, mutation=False):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except Exception:
            raise APIError('Please sign in.', 401)
        key = '__Host-harbor' if self.server.tls else 'harbor'
        token = cookies[key].value if key in cookies else ''
        with self.app.lock:
            session = self.app.sessions.get(token)
            if not session or session['expires'] <= time.monotonic():
                self.app.sessions.pop(token, None)
                raise APIError('Please sign in.', 401)
            if mutation and not hmac.compare_digest(self.headers.get('X-Harbor-CSRF', ''), session['csrf']):
                raise APIError('The security token is missing or expired. Refresh and try again.', 403)
        return token, session

    def body(self, limit=32768):
        if self.headers.get('Transfer-Encoding'):
            raise APIError('Chunked requests are not supported.')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise APIError('Invalid content length.')
        if length < 0 or length > limit:
            raise APIError('This request is too large.', 413)
        body = self.rfile.read(length)
        if len(body) != length:
            raise APIError('The upload was interrupted.')
        return body

    def json_body(self,limit=32768):
        if self.headers.get_content_type() != 'application/json':
            raise APIError('Expected a JSON request.', 415)
        try:
            data = json.loads(self.body(limit))
        except (ValueError, UnicodeDecodeError):
            raise APIError('Invalid JSON.')
        if not isinstance(data, dict):
            raise APIError('Expected a JSON object.')
        return data

    def login_reply(self, token, session):
        key = '__Host-harbor' if self.server.tls else 'harbor'
        secure = '; Secure' if self.server.tls else ''
        self.reply({'username': session['username'], 'role':session['role'],'csrf': session['csrf']},
                   cookie=f'{key}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}')

    def do_GET(self):
        try:
            self.get()
        except APIError as error:
            self.reply({'error': str(error)}, error.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception as error:
            print(f'Request failed: {type(error).__name__}', flush=True)
            self.reply({'error': 'The server could not complete the request. Check the system journal.'}, 500)

    def get(self):
        self._file_app=None
        self.console_host()
        url = urlsplit(self.path)
        route, query = url.path, parse_qs(url.query)
        if route == '/api/health':
            return self.reply({'name': 'Harbour OS', 'version': VERSION, 'setup_required': self.app.admin is None, 'demo': self.app.demo,
                'local_console':self.server.local_console,'live':os.getenv('HARBOR_LIVE')=='1','onboarding_complete':self.app.config.get('onboarding_complete',True)})
        if route == '/api/setup-session':
            self.require_local_console()
            if self.app.admin:
                raise APIError('An administrator already exists.',409)
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
            with self.app.lock:
                self.app.setup_sessions={k:v for k,v in self.app.setup_sessions.items() if v['expires']>time.monotonic()}
                if len(self.app.setup_sessions)>=32:self.app.setup_sessions.pop(next(iter(self.app.setup_sessions)))
                self.app.setup_sessions[token]={'csrf':csrf,'expires':time.monotonic()+900}
            return self.reply({'csrf':csrf},cookie=f'harbor-setup={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=900')
        if route.startswith('/api/'):
            _, session = self.session()
            if route == '/api/session':
                return self.reply({'username': session['username'], 'role':session['role'],'csrf': session['csrf']})
            if session['role']!='owner' and route not in ('/api/summary','/api/files','/api/shares','/api/download','/api/archive','/api/preview','/api/image','/api/apps','/api/catalog','/api/trash','/api/jobs'):
                raise APIError('This feature is available to the server owner.',403)
            self.file_volume(route,query,session)
            if route == '/api/app-settings':return self.reply(self.app.app_settings.info(query.get('id',[''])[0],query.get('path',[None])[0]))
            if route == '/api/app-location':return self.reply(self.app.app_settings.system_location())
            if route == '/api/external-drives':return self.reply(dict(disks=self.app.external_drives.inventory(),support=self.app.external_drives.support()))
            if route == '/api/external-files':return self.reply(self.app.external_drives.files(query.get('id',[''])[0],query.get('path',[''])[0]))
            if route == '/api/external-download':
                path=self.app.external_drives.path(query.get('id',[''])[0],query.get('path',[''])[0])
                if not path.is_file():raise APIError('Choose a regular file.',409)
                from urllib.parse import quote
                with path.open('rb') as stream:
                    self.send_response(200);self.headers_common()
                    self.send_header('Content-Type','application/octet-stream')
                    self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(path.name))
                    self.send_header('Content-Length',str(path.stat().st_size));self.end_headers()
                    shutil.copyfileobj(stream,self.wfile,256*1024)
                return
            if route == '/api/recovery':return self.reply(self.app.recovery.info())
            if route == '/api/system-files':return self.reply(self.app.system_files.info())
            if route == '/api/members':return self.reply(self.app.members.public())
            if route == '/api/system':return self.reply(self.app.system_settings.info())
            if route == '/api/network':return self.reply(self.app.networking.info())
            if route == '/api/os-updates':return self.reply(self.app.releases.info())
            if route == '/api/summary':
                return self.reply(self.app.summary())
            if route == '/api/disks':
                return self.reply(self.app.disks())
            if route == '/api/storage/members':
                return self.reply(self.app.storage_manager.lifecycle_info())
            if route == '/api/storage/disks':
                return self.reply({'disks':self.app.storage_manager.wipe_inventory(),'levels':LEVELS,'live':os.getenv('HARBOR_LIVE')=='1'})
            if route == '/api/shares':
                return self.reply([s for s in self.app.config['shares'] if self.app.members.allowed(s,session['username'])])
            if route == '/api/files':
                relative=query.get('path',[''])[0]
                checked=self.app.access_path(relative,session['username'],allow_root=True)
                parts=checked.relative_to((self.app.storage/'shares').resolve()).parts
                canonical='/'.join(parts)
                result=self.app.files(canonical)
                if not parts:result['entries']=[e for e in result['entries'] if any(s['name']==e['name'] and self.app.members.allowed(s,session['username']) for s in self.app.config['shares'])]
                result['writable']=bool(parts) and any(s['name']==parts[0] and self.app.members.allowed(s,session['username'],True) for s in self.app.config['shares'])
                return self.reply(result)
            if route == '/api/trash':
                return self.reply([t for t in self.app.file_operations.trash() if any(s['name']==t['path'].split('/')[0] and self.app.members.allowed(s,session['username'],True) for s in self.app.config['shares'])])
            if route == '/api/preview':
                path=self.app.access_path(query.get('path',[''])[0],session['username'])
                if not path.is_file() or path.stat().st_size>2*1024*1024:raise APIError('Preview is available for files under 2 MB.',409)
                if path.suffix.lower() not in ('.txt','.md','.json','.log','.csv','.yaml','.yml','.ini','.conf','.xml','.py','.sh'):
                    raise APIError('Download this file to view it.',409)
                return self.reply({'name':path.name,'text':path.read_text(encoding='utf-8',errors='replace')})
            if route == '/api/image':
                path=self.app.access_path(query.get('path',[''])[0],session['username'])
                types={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif','.webp':'image/webp'}
                if not path.is_file() or path.suffix.lower() not in types or path.stat().st_size>16*1024**2:raise APIError('Image preview is unavailable.',409)
                self.send_response(200);self.headers_common();self.send_header('Content-Type',types[path.suffix.lower()]);self.send_header('Content-Length',str(path.stat().st_size));self.end_headers()
                with path.open('rb') as stream:shutil.copyfileobj(stream,self.wfile,256*1024)
                return
            if route == '/api/snapshots':
                return self.reply(self.app.snapshots())
            if route == '/api/apps':
                return self.reply(self.app.app_list())
            if route == '/api/catalog':
                return self.reply({k:v for k,v in CATALOG_INFO.items() if k!='apps'})
            if route == '/api/storage/expansion':
                return self.reply(self.app.storage_manager.expansion_info())
            if route == '/api/events':
                return self.reply(self.app.events)
            if route == '/api/jobs':
                self.app.system_settings.external_status()
                return self.reply([j for j in list(self.app.jobs.values())[::-1] if session['role']=='owner' or j.get('actor')==session['username']])
            if route == '/api/download':
                path = self.app.access_path(query.get('path',[''])[0],session['username'])
                if not path.is_file():
                    raise APIError('File not found.', 404)
                from urllib.parse import quote
                self.send_response(200)
                self.headers_common()
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(path.name))
                self.send_header('Content-Length', str(path.stat().st_size))
                self.end_headers()
                with path.open('rb') as stream:
                    shutil.copyfileobj(stream, self.wfile, 256 * 1024)
                return
            if route == '/api/archive':
                selected=query.get('path',[])
                if not 1<=len(selected)<=20:raise APIError('Choose between 1 and 20 files or folders.')
                roots=[self.app.access_path(p,session['username']) for p in selected]
                entries={};total=0;base=(self.app.storage/'shares').resolve()
                for selected_path in roots:
                    if selected_path.is_file():candidates=[selected_path]
                    elif selected_path.is_dir():
                        candidates=[]
                        for directory,folders,files in os.walk(selected_path,followlinks=False):
                            folders[:]=[n for n in folders if not (Path(directory)/n).is_symlink()]
                            candidates.extend(Path(directory)/name for name in files if not name.startswith('.harbour-upload-') and not (Path(directory)/name).is_symlink())
                            if len(candidates)>10000:raise APIError('Use SMB to download folders containing more than 10,000 files.',413)
                        if not candidates:candidates=[selected_path]
                    else:raise APIError('A selected file is unavailable.',404)
                    for path in candidates:
                        archive_name=path.relative_to(base).as_posix()
                        if archive_name in entries:continue
                        entries[archive_name]=path;total+=path.stat().st_size if path.is_file() else 0
                        if total>16*1024**3 or len(entries)>10000:raise APIError('Use SMB for downloads larger than 16 GB or 10,000 files.',413)
                if not self.app.archive_slots.acquire(blocking=False):raise APIError('Two archive downloads are already running. Try again shortly.',429)
                try:
                    from urllib.parse import quote
                    name=(roots[0].name if len(roots)==1 else 'Harbour-files')+'.zip'
                    self.send_response(200);self.headers_common();self.send_header('Content-Type','application/zip')
                    self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(name));self.send_header('Connection','close');self.end_headers();self.close_connection=True
                    with zipfile.ZipFile(self.wfile,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
                        for name,path in entries.items():archive.write(path,name)
                finally:self.app.archive_slots.release()
                return
            raise APIError('Endpoint not found.', 404)
        static = {'/': 'index.html', '/app.js': 'app.js', '/onboarding.js':'onboarding.js','/desktop.js':'desktop.js','/desktop.css':'desktop.css','/features.js':'features.js', '/style.css': 'style.css', '/favicon.svg': 'favicon.svg'}
        static['/transfers.js']='transfers.js'
        static['/drives.js']='drives.js'
        static['/clarity.css']='clarity.css'
        static['/recovery.js']='recovery.js'
        static.update({'/process.js':'process.js','/widgets.js':'widgets.js','/refinements.css':'refinements.css'})
        static.update({'/maintenance.js':'maintenance.js','/maintenance.css':'maintenance.css','/theme.js':'theme.js','/experience.js':'experience.js','/experience.css':'experience.css','/wallpaper.svg':'wallpaper.svg'})
        if route.startswith('/catalog/icons/'):
            name=route.removeprefix('/catalog/icons/')
            if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,70}\.(svg|png|jpg|jpeg|webp|gif)',name):
                raise APIError('Icon not found.',404)
            path=Path(__file__).parent/'catalog/icons'/name
            if not path.is_file():
                raise APIError('Icon not found.',404)
        elif route not in static:
            raise APIError('Page not found.', 404)
        else:
            path = WEB / static[route]
        content = path.read_bytes()
        self.send_response(200)
        self.headers_common()
        self.send_header('Content-Type', (mimetypes.guess_type(path.name)[0] or 'application/octet-stream') + '; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        try:
            self.post()
        except APIError as error:
            self.close_connection = True
            self.reply({'error': str(error)}, error.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception as error:
            print(f'Mutation failed: {type(error).__name__}', flush=True)
            self.close_connection = True
            self.reply({'error': 'The server could not complete the request. Check the system journal.'}, 500)

    def post(self):
        self._file_app=None
        self.console_host()
        url = urlsplit(self.path)
        route, query = url.path, parse_qs(url.query)
        # JSON-only authentication endpoints + SameSite cookies prevent form-based CSRF.
        origin = self.headers.get('Origin')
        expected = ('https' if self.server.tls else 'http') + '://' + self.headers.get('Host', '')
        if origin and origin != expected:
            raise APIError('Cross-origin requests are not allowed.', 403)
        if route in ('/api/login', '/api/setup'):
            data = self.json_body(2*1024**2 if route=='/api/app-settings' else 32768)
            if route == '/api/setup':
                self.require_local_console()
                if self.app.admin:raise APIError('This server already has an administrator.',409)
                cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
                token=cookies['harbor-setup'].value if 'harbor-setup' in cookies else ''
                with self.app.lock:
                    session=self.app.setup_sessions.get(token)
                    if not session or session['expires']<=time.monotonic() or not hmac.compare_digest(self.headers.get('X-Harbor-CSRF',''),session['csrf']):
                        raise APIError('Refresh the graphical setup screen and try again.',403)
                return self.login_reply(*self.app.setup(data,self.client_address[0],local_authorized=True))
            return self.login_reply(*self.app.login(data.get('username', ''), data.get('password', ''), self.client_address[0]))
        token, session = self.session(mutation=True)
        if session['role']!='owner' and route not in ('/api/logout','/api/upload','/api/folders','/api/file-action','/api/trash-restore'):
            raise APIError('This feature is available to the server owner.',403)
        self.file_volume(route,query,session)
        if route=='/api/external-upload':
            if self.headers.get('Transfer-Encoding') or self.headers.get_content_type()!='application/octet-stream':raise APIError('Send files as a binary upload.')
            try:length=int(self.headers.get('Content-Length','-1'))
            except ValueError:raise APIError('Invalid upload size.')
            return self.reply(self.app.external_drives.upload(query.get('id',[''])[0],query.get('path',[''])[0],query.get('name',[''])[0],self.rfile,length),201)
        if route=='/api/os-updates/upload':
            if self.headers.get('Transfer-Encoding') or self.headers.get_content_type()!='application/octet-stream':raise APIError('Send a signed update bundle as a binary upload.')
            try:length=int(self.headers.get('Content-Length','-1'))
            except ValueError:raise APIError('Invalid upload length.')
            return self.reply(self.app.releases.receive(self.rfile,length),201)
        if route == '/api/upload':
            self.app.require_storage()
            self.app.access_path(query.get('path',[''])[0],session['username'],write=True)
            directory = contained_path(self.app.storage / 'shares', query.get('path', [''])[0])
            name = query.get('name', [''])[0]
            if not name or name in ('.', '..') or '/' in name or '\\' in name or len(name) > 200 or any(ord(c) < 32 for c in name):
                raise APIError('Invalid filename.')
            target = contained_path(directory, name)
            if not directory.is_dir() or directory == (self.app.storage / 'shares').resolve():
                raise APIError('Choose a shared folder before uploading.')
            if target.exists():
                raise APIError('A file with that name already exists.', 409)
            if self.headers.get('Transfer-Encoding'):raise APIError('Chunked requests are not supported.')
            try:length=int(self.headers.get('Content-Length','-1'))
            except ValueError:raise APIError('Invalid content length.')
            if not 0<=length<=MAX_UPLOAD:raise APIError('Upload a file under 1 GB, or use SMB.',413)
            if hasattr(self.app,'check_upload_space'):self.app.check_upload_space(length)
            temporary=directory/('.harbour-upload-'+secrets.token_hex(16))
            try:
                with temporary.open('xb') as stream:
                    remaining=length
                    while remaining:
                        chunk=self.rfile.read(min(1024*1024,remaining))
                        if not chunk:raise APIError('The upload was interrupted.')
                        stream.write(chunk);remaining-=len(chunk)
                    stream.flush();os.fsync(stream.fileno())
                transfer(temporary,target)
                self.app.owner(target)
            except FileExistsError:
                raise APIError('A file with that name already exists.', 409)
            finally:temporary.unlink(missing_ok=True)
            self.app.event(f'Uploaded “{name}”.')
            return self.reply({'name': name}, 201)
        data = self.json_body(2*1024**2 if route=='/api/app-settings' else 32768)
        if route=='/api/network-plan':return self.reply(self.app.networking.plan(data))
        if route=='/api/network-action':return self.reply(self.app.networking.action(data),202)
        if route=='/api/os-updates/action':return self.reply(self.app.releases.action(data),202)
        if route == '/api/members':return self.reply(self.app.members.create(data),201)
        if route == '/api/member-state':return self.reply(self.app.members.enable(data))
        if route == '/api/share-access':return self.reply(self.app.members.access(data))
        if route == '/api/system-action':return self.reply(self.app.system_settings.action(data),202)
        if route == '/api/file-action':
            operation=data.get('operation')
            self.app.access_path(data.get('path',''),session['username'],write=operation!='copy')
            if operation in ('copy','move'):self.app.access_path(data.get('destination',''),session['username'],write=True)
            return self.reply(self.app.job('File '+str(operation),lambda:self.app.file_operations.action(data,session['username']),actor=session['username']),202)
        if route == '/api/trash-restore':
            item=next((t for t in self.app.file_operations.trash() if t['id']==data.get('id')),None)
            if not item:raise APIError('Recycle-bin item not found.',404)
            self.app.access_path(item['path'],session['username'],write=True)
            return self.reply(self.app.file_operations.restore(item['id']))
        if route == '/api/onboarding':
            self.app.config['onboarding_complete']=True
            self.app.save()
            return self.reply({'ok':True})
        if route == '/api/logout':
            with self.app.lock:
                self.app.sessions.pop(token, None)
            key = '__Host-harbor' if self.server.tls else 'harbor'
            return self.reply({'ok': True}, cookie=f'{key}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0' + ('; Secure' if self.server.tls else ''))
        if route == '/api/shares':
            return self.reply(self.app.create_share(data.get('name', '')), 201)
        if route == '/api/folders':
            self.app.require_storage()
            self.app.access_path(data.get('path',''),session['username'],write=True)
            parent = contained_path(self.app.storage / 'shares', data.get('path', ''))
            if parent == (self.app.storage / 'shares').resolve():
                raise APIError('Create a shared folder from the Sharing page first.')
            try:name=filename(data.get('name',''))
            except ValueError as error:raise APIError(str(error))
            path = contained_path(parent,name)
            try:
                path.mkdir()
            except FileExistsError:
                raise APIError('That folder already exists.', 409)
            self.app.owner(path)
            return self.reply({'name': path.name}, 201)
        if route == '/api/snapshots':
            return self.reply(self.app.job('Create snapshot', lambda: self.app.snapshot(data.get('share', ''))), 202)
        if route == '/api/restore':
            return self.reply(self.app.job('Restore snapshot', lambda: self.app.restore(data.get('snapshot', ''), data.get('name', ''))), 202)
        if route == '/api/app-settings':return self.reply(self.app.app_settings.save(data),202)
        if route == '/api/external-file-action':return self.reply(self.app.external_drives.file_action(data))
        if route == '/api/external-action':return self.reply(self.app.external_drives.action(data))
        if route == '/api/filesystem-support':return self.reply(self.app.external_drives.install_support(),202)
        if route == '/api/virtualization': return self.reply(self.app.virtualization.status())
        if route == '/api/vms': return self.reply(self.app.virtual_machines.info())
        if route == '/api/virtualization-install': return self.reply(self.app.virtualization.install(),202)
        if route == '/api/vm-action': return self.reply(self.app.virtual_machines.action(data))
        if route == '/api/app-action':
            return self.reply(self.app.app_action(data.get('id', ''), data.get('action', ''),data.get('options')), 202)
        if route == '/api/app-plan':
            return self.reply(self.app.app_plan(data.get('id',''),data.get('options')))
        if route == '/api/storage/member-resume':
            return self.reply(self.app.storage_manager.lifecycle_resume(data),202)
        if route == '/api/recovery/prepare':return self.reply(self.app.recovery.prepare(),202)
        if route == '/api/recovery/boot':return self.reply(self.app.recovery.boot(data),202)
        if route == '/api/storage/checkpoint':
            return self.reply(self.app.storage_manager.lifecycle_checkpoint())
        if route == '/api/storage/member-plan':
            return self.reply(self.app.storage_manager.lifecycle_plan(data))
        if route == '/api/storage/recover-mount':
            return self.reply(self.app.storage_manager.recover_mount(data))
        if route == '/api/storage/member-action':
            return self.reply(self.app.storage_manager.lifecycle_action(data),202)
        if route == '/api/storage/expand-plan':
            return self.reply(self.app.storage_manager.expand_plan(data))
        if route == '/api/storage/expand':
            return self.reply(self.app.storage_manager.expand(data),202)
        if route == '/api/storage/wipe-plan':
            return self.reply(self.app.storage_manager.wipe_plan(data))
        if route == '/api/storage/wipe':
            return self.reply(self.app.storage_manager.wipe_disk(data),202)
        if route == '/api/storage/plan':
            return self.reply(self.app.storage_manager.plan(data))
        if route == '/api/storage/create':
            return self.reply(self.app.storage_manager.create(data),202)
        if route == '/api/smart':
            if self.app.demo:
                raise APIError('Disk health checks require the appliance.', 409)
            path = data.get('path')
            allowed = {disk['path'] for disk in self.app.disks() if disk['type'] == 'disk' and disk['size'] > 0}
            if path not in allowed:
                raise APIError('Unknown disk.')
            result = run('smartctl', '-H', '-A', '-j', path, timeout=30, check=False)
            try:
                report = json.loads(result.stdout)
                from drive_health import assessment
                report.update(assessment(report))
                if report['health']=='failing':
                    report['harbor_assessment'] = 'Failing drive: '+ '; '.join(report['health_reasons']) + '. Pool use is allowed after reviewing this warning. Back up your data and replace the drive promptly.'
                return self.reply(report)
            except ValueError:
                raise APIError('SMART data is unavailable for this disk.', 409)
        raise APIError('Endpoint not found.', 404)


def make_server(app, host='127.0.0.1', port=8088, cert=None, key=None,local_console=False):
    if host not in ('127.0.0.1', 'localhost', '::1') and not (cert and key):
        raise RuntimeError('TLS is required when listening beyond localhost.')
    server = ThreadingHTTPServer((host, port), Handler)
    server.app = app
    server.tls = bool(cert and key)
    server.local_console = bool(local_console or app.demo)
    if server.tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Harbor OS management service')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--port', type=int, default=int(os.getenv('HARBOR_PORT', '8088')))
    args = parser.parse_args()
    if args.demo:
        base = Path(os.getenv('HARBOR_DEMO_ROOT',str(Path(__file__).resolve().parents[1] / '.local' / 'preview')))
        app = Harbor(base / 'state', base / 'storage', base / 'apps', demo=True)
    else:
        app = Harbor()
    host = '127.0.0.1' if args.demo else os.getenv('HARBOR_HOST', '127.0.0.1')
    server = make_server(app, host, args.port, os.getenv('HARBOR_TLS_CERT'), os.getenv('HARBOR_TLS_KEY'))
    print(f'Harbor OS {VERSION} listening at {"https" if server.tls else "http"}://{host}:{server.server_port}', flush=True)
    if not args.demo:
        console=make_server(app,'127.0.0.1',17080,local_console=True)
        threading.Thread(target=console.serve_forever,daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.pool.shutdown(wait=False, cancel_futures=True)

