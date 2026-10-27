"""Pinned official ZimaOS catalog and Harbor's Docker Compose adapter."""
import copy
import json
import os
import stat
from pathlib import Path, PurePosixPath
import re

CATALOG_ROOT = Path(__file__).parent / 'catalog'
CATALOG_INFO = json.loads((CATALOG_ROOT / 'official.json').read_text(encoding='utf-8'))
OFFICIAL = {item['id']: item for item in CATALOG_INFO['apps']}
VARIABLE = re.compile(r'\$\$|\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-|-)([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)')


def project_name(ident):
    return 'harbor-'+re.sub(r'[^a-z0-9_-]','-',ident)


def expand(value, variables):
    if isinstance(value, str):
        # Compose expands dollars too; emit escaped literals after our single expansion.
        def replacement(match):
            if match[0]=='$$':
                return '$'
            name = match[1] or match[4]
            if name not in variables and match[3] is None:
                return match[0]
            result = str(variables.get(name, ''))
            return result if result else (match[3] or '')
        return VARIABLE.sub(replacement, value).replace('$', '$$')
    if isinstance(value, list):
        return [expand(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: expand(v, variables) for k, v in value.items()}
    return value


def environment(service):
    result = service.get('environment') or {}
    if isinstance(result, list):
        result = dict(item.split('=', 1) if '=' in item else (item, '') for item in result)
    return {str(k): '' if v is None else str(v) for k,v in result.items()}


# These are optional acceleration mappings in the pinned standard Jellyfin entry.
# Never drop arbitrary app mounts or create fake host hardware directories.
JELLYFIN_OPTIONAL_DEVICES = {'/dev/dri', '/dev/vcsm', '/dev/vchiq', '/dev/video10', '/dev/video11', '/dev/video12'}


def jellyfin_hardware(service):
    omitted=[]
    devices=[]
    for device in service.get('devices', []):
        parts=device.split(':') if isinstance(device,str) else []
        source=parts[0] if parts else device.get('source','') if isinstance(device,dict) else ''
        target=parts[1] if len(parts)>1 else source if parts else device.get('target','') if isinstance(device,dict) else ''
        if source in JELLYFIN_OPTIONAL_DEVICES and target==source and not Path(source).exists():
            omitted.append(source)
        else:
            devices.append(device)
    if devices:service['devices']=devices
    else:service.pop('devices',None)
    volumes=[]
    for volume in service.get('volumes', []):
        parts=volume.split(':') if isinstance(volume,str) else []
        source=parts[0] if parts else volume.get('source','')
        target=parts[1] if len(parts)>1 else '' if parts else volume.get('target','')
        if source==target=='/opt/vc/lib' and not Path(source).exists():
            omitted.append(source)
        else:
            volumes.append(volume)
    service['volumes']=volumes
    return omitted


def prepare(ident, apps, storage, uid=1000, gid=1000, options=None):
    item = OFFICIAL[ident]
    options = options or {}
    if not isinstance(options, dict) or not isinstance(options.get('environment', {}), dict):
        raise ValueError('Invalid application settings.')
    spec = copy.deepcopy(item['compose'])
    if not spec.get('services'):
        raise ValueError('This catalog entry has no services.')
    variables = {'AppID': ident, 'PUID': str(uid), 'PGID': str(gid), 'TZ':'Etc/UTC', 'HOSTNAME':'harbor'}
    spec = expand(spec, variables)
    spec.pop('name', None)
    spec.pop('x-casaos', None)
    spec.pop('version', None)
    warnings, fields, ports, compatibility = [], [], [], []
    allowed_fields = set()
    for name, service in spec['services'].items():
        if not isinstance(service, dict) or not service.get('image') or service.get('build'):
            raise ValueError('This entry needs a source build and cannot be installed from the store.')
        service.pop('x-casaos', None)
        service.pop('container_name', None)
        if ident=='jellyfin':
            omitted=jellyfin_hardware(service)
            if omitted:
                compatibility.append(f"{name}: unavailable optional hardware skipped ({', '.join(omitted)}). Software playback remains available.")
        if service.get('privileged'):
            warnings.append(f'{name}: privileged container, with full device access')
        if service.get('network_mode') == 'host':
            warnings.append(f'{name}: shares the server network')
        if service.get('pid') == 'host':
            warnings.append(f'{name}: shares host processes')
        if service.get('cap_add'):
            warnings.append(f"{name}: extra capabilities: {', '.join(service['cap_add'])}")
        if service.get('devices'):
            warnings.append(f'{name}: direct hardware device access')
        if service.get('env_file') or service.get('extends'):
            raise ValueError('This entry requires external configuration files.')
        values = environment(service)
        for key, original in values.items():
            field = name + '.' + key
            allowed_fields.add(field)
            value = options.get('environment', {}).get(field, original)
            if not isinstance(value, str) or len(value) > 4096 or '\x00' in value:
                raise ValueError('Invalid environment setting.')
            fields.append({'id':field, 'name':key, 'service':name, 'value':value})
            values[key] = value.replace('$','$$') if field in options.get('environment', {}) else value
        service['environment'] = values
        volumes=[]
        for volume in service.get('volumes', []):
            if isinstance(volume, str):
                parts=volume.split(':')
                if len(parts)==1:
                    volumes.append(volume)
                    continue
                volume={'type':'bind' if parts[0].startswith(('/','.')) else 'volume','source':parts[0], 'target':parts[1], 'read_only':'ro' in parts[2:]}
            source=str(volume.get('source',''))
            if volume.get('type')=='bind':
                if source == '/DATA/AppData/'+ident or source.startswith('/DATA/AppData/'+ident+'/'):
                    volume['source']=str(PurePosixPath(apps)/ident)+source[len('/DATA/AppData/'+ident):]
                elif source.startswith('/DATA/AppData'):
                    volume['source']=str(PurePosixPath(apps)/ident/'shared')+source[len('/DATA/AppData'):]
                elif source == '/DATA' or source.startswith('/DATA/'):
                    volume['source']=str(PurePosixPath(storage)/'shares')+source[len('/DATA'):]
                else:
                    warnings.append(f"{name}: host path {source} → {volume.get('target','')}")
                if '..' in PurePosixPath(volume['source']).parts or not PurePosixPath(volume['source']).is_absolute():
                    raise ValueError('The app contains an invalid host mount.')
            volumes.append(volume)
        service['volumes']=volumes
        for port in service.get('ports', []):
            if isinstance(port, dict):
                published=str(port.get('published',''))
                ports.append(published+'/'+str(port.get('protocol','tcp')))
            else:
                ports.append(str(port))
    if set(options.get('environment', {})) - allowed_fields:
        raise ValueError('Unknown application setting.')
    if any(not isinstance(value,dict) or not isinstance(value.get('content'),str) for value in spec.get('configs',{}).values()) or spec.get('secrets') or spec.get('include'):
        raise ValueError('This entry requires external secret or configuration files.')
    arch=item.get('architectures') or []
    if arch and 'amd64' not in arch and 'x86_64' not in arch:
        raise ValueError('This application does not support x86-64 computers.')
    return {'compose':spec,'environment':fields,'warnings':sorted(set(warnings)),'ports':ports,'compatibility':compatibility}


def public_item(item):
    return {k:v for k,v in item.items() if k not in ('compose','detail','screenshots')}


def compose_app_state(item, containers):
    """Successful dependency setup jobs are not stopped application daemons."""
    services=item.get('compose',{}).get('services',{})
    helpers=set()
    for service in services.values():
        dependencies=service.get('depends_on',{})
        if isinstance(dependencies,dict):
            helpers.update(name for name,rule in dependencies.items() if isinstance(rule,dict) and rule.get('condition')=='service_completed_successfully')
    runtime=[]
    for container in containers:
        labels=dict(field.split('=',1) for field in container.get('Labels','').split(',') if '=' in field)
        if labels.get('com.docker.compose.oneoff','').lower()=='true':continue
        service=labels.get('com.docker.compose.service')
        complete=container.get('State')=='exited' and bool(re.match(r'^Exited \(0\)(?: |$)',container.get('Status','')))
        if service in helpers and complete:continue
        runtime.append((service,container.get('State')))
    if not runtime:return 'stopped'
    if any(state=='restarting' for _,state in runtime):return 'restarting'
    if all(state=='running' for _,state in runtime) and (not item.get('main') or any(service==item['main'] for service,_ in runtime)):return 'running'
    return 'stopped'


def provision_app_mounts(ident, compose, apps, storage):
    """Create managed bind directories; prepare AnythingLLM's documented UID 1000."""
    apps_root=Path(apps).resolve();shares_root=(Path(storage)/'shares').resolve()
    for service in compose.get('services',{}).values():
        for volume in service.get('volumes',[]):
            if not isinstance(volume,dict) or volume.get('type')!='bind':continue
            source=Path(volume['source'])
            anything_storage=ident=='anythingllm' and volume.get('target')=='/app/server/storage'
            if anything_storage:
                expected=apps_root/'anythingllm'/'storage'
                if source.resolve()!=expected or source.is_symlink() or expected.parent.is_symlink():
                    raise ValueError('AnythingLLM storage must be its dedicated app directory without symlinks.')
            if any(source.resolve().is_relative_to(root) for root in (apps_root,shares_root)):
                source.mkdir(parents=True,exist_ok=True)
            if not anything_storage:continue
            # No recursive ownership changes, shared-folder changes or world-writable modes.
            mode=stat.S_IMODE(source.stat().st_mode)
            os.chown(source,1000,1000)
            os.chmod(source,mode|0o700)
