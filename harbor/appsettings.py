"""Owner app configuration editor with rollback and OS-drive placement checks."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

TEXT = {'.json', '.yaml', '.yml', '.toml', '.ini', '.conf', '.cfg', '.xml', '.txt', '.properties', '.env'}


class AppSettings:
    def __init__(self, app, run, error, atomic):
        self.app, self.run, self.error, self.atomic = app, run, error, atomic

    def system_location(self,check_space=False):
        roots = (self.app.apps, self.app.state)
        for root in roots:
            if any(p.is_symlink() for p in (root, *root.parents)):
                raise self.error('App storage is redirected. Review the system-drive location.', 409)
            root.mkdir(parents=True, exist_ok=True)
            if not self.app.demo and root.stat().st_dev != Path('/').stat().st_dev:
                raise self.error('Apps and their configuration must be on the OS drive.', 409)
        usage = shutil.disk_usage(self.app.apps)
        if check_space and usage.free < min(2*1024**3, usage.total//20):
            raise self.error('Free space on the OS drive before changing applications.', 409)
        return dict(data=str(self.app.apps), configuration=str(self.app.state/'compose'),
                    location='OS drive', free=usage.free)

    def paths(self, ident):
        from appstore import OFFICIAL
        if ident not in OFFICIAL:
            raise self.error('Unknown application.')
        config = self.app.state/'compose'/ident/'compose.json'
        if not config.is_file() or any(p.is_symlink() for p in (config, *config.parents)):
            raise self.error('This app has no editable installed configuration.', 409)
        return config, self.app.apps/ident

    def file(self, ident, relative):
        _, root = self.paths(ident)
        if not isinstance(relative, str) or not relative or len(relative)>1000:
            raise self.error('Choose a configuration file.')
        path = root/relative
        if not path.resolve().is_relative_to(root.resolve()) or any(p.is_symlink() for p in (path, *path.parents)):
            raise self.error('Configuration files must stay inside this app folder.', 403)
        if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > 1024**2:
            raise self.error('Only regular configuration files under 1 MiB can be edited.', 409)
        if path.suffix.lower() not in TEXT and not path.name.startswith('.env'):
            raise self.error('This file type is not a text configuration.', 409)
        try:
            if '\x00' in path.read_text(encoding='utf-8'):
                raise ValueError()
        except (UnicodeError, ValueError):
            raise self.error('This file is not editable UTF-8 text.', 409)
        return path

    def info(self, ident, relative=None):
        config, root = self.paths(ident)
        if relative is not None:
            path = self.file(ident, relative)
            return dict(path=relative, content=path.read_text(encoding='utf-8'),
                        revision=hashlib.sha256(path.read_bytes()).hexdigest())
        files = []
        if root.is_dir() and not root.is_symlink():
            count = 0
            for directory, folders, names in os.walk(root, followlinks=False):
                folders[:] = [n for n in folders if not (Path(directory)/n).is_symlink()]
                for name in names:
                    count += 1
                    if count > 5000:break
                    path = Path(directory)/name
                    if path.suffix.lower() in TEXT or name.startswith('.env'):
                        try:self.file(ident, path.relative_to(root).as_posix())
                        except self.error:continue
                        files.append(path.relative_to(root).as_posix())
                    if len(files)>=200:break
                if count>5000 or len(files)>=200:break
        return dict(id=ident, location=self.system_location(), data_path=str(root),
                    compose=json.loads(config.read_text()), revision=hashlib.sha256(config.read_bytes()).hexdigest(),
                    files=sorted(files), note='Settings may contain passwords. Saving recreates this app; keep a backup.')

    def save(self, data):
        ident = data.get('id');config, _ = self.paths(ident)
        if data.get('confirmation') != 'APPLY '+ident:
            raise self.error('Type APPLY '+ident+' to restart with these settings.')
        self.system_location(True)
        relative = data.get('path')
        target = self.file(ident, relative) if relative is not None else config
        original = target.read_bytes()
        if hashlib.sha256(original).hexdigest() != data.get('revision'):
            raise self.error('Settings changed since you opened them. Reopen and review.', 409)
        if relative is None:
            value = data.get('compose')
            if not isinstance(value, dict) or not isinstance(value.get('services'), dict) or not value['services']:
                raise self.error('Enter a Compose JSON object with services.')
            if any(k in value for k in ('include', 'secrets')):
                raise self.error('External includes and secret files are not supported here.')
            for name, service in value['services'].items():
                if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,80}', name) or not isinstance(service, dict) or service.get('build') or not service.get('image'):
                    raise self.error('Use image-based Compose services.')
                if any(k in service for k in ('env_file', 'extends')):
                    raise self.error('External environment and extends files are not supported here.')
            updated = (json.dumps(value, indent=2)+'\n').encode()
        else:
            content = data.get('content')
            if not isinstance(content, str) or '\x00' in content:
                raise self.error('Enter text configuration content.')
            updated = content.encode('utf-8')
        if len(updated)>1024**2:raise self.error('Configuration exceeds 1 MiB.', 413)
        def execute():
            with self.app.lock:
                if any(j.get('kind')=='app' and j.get('target')==ident and j.get('state') in ('queued','running') and j.get('id')!=getattr(self.app.job_context,'ident',None) for j in self.app.jobs.values()):
                    raise self.error('Wait for the other app operation to finish.', 409)
                checked = self.file(ident, relative) if relative is not None else self.paths(ident)[0]
                if hashlib.sha256(checked.read_bytes()).hexdigest()!=data['revision']:
                    raise self.error('Configuration changed. Reopen and review.', 409)
                stat=checked.stat()
                def write(content):
                    fd, name=tempfile.mkstemp(prefix='.harbour-settings-', dir=checked.parent)
                    try:
                        with os.fdopen(fd,'wb') as stream:
                            stream.write(content);stream.flush();os.fsync(stream.fileno())
                        os.chmod(name,stat.st_mode & 0o777)
                        if not self.app.demo:os.chown(name,stat.st_uid,stat.st_gid)
                        os.replace(name,checked)
                    finally:Path(name).unlink(missing_ok=True)
                from appstore import project_name
                command=(['docker-compose'] if shutil.which('docker-compose') else ['docker','compose'])+['--project-name',project_name(ident),'--file',str(config)]
                self.app.job_progress('Validating settings','Checking app configuration before restart.')
                write(updated)
                try:
                    self.run(*command,'config','--quiet',timeout=30)
                    self.app.job_progress('Applying settings','Recreating the application with your configuration.')
                    self.run(*command,'up','-d','--force-recreate',timeout=300)
                except Exception:
                    write(original)
                    self.run(*command,'up','-d','--force-recreate',timeout=300,check=False)
                    raise self.error('Could not apply settings. The previous file was restored.',409)
                return dict(app=ident, saved=True, restarted=True)
        return self.app.job('Apply '+ident+' settings',execute,kind='app',target=ident)
