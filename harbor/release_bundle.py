"""V1 signed release format: authenticated manifest, bounded payload, fixed destinations."""
import ast,hashlib,io,json,re,subprocess,tarfile,tempfile,zipfile
from pathlib import Path,PurePosixPath

LIMIT=64*1024**2
HELPERS={'harbour-network-change':'/usr/local/sbin/harbour-network-change','harbor-init':'/usr/local/sbin/harbor-init','harbor-console':'/usr/local/sbin/harbor-console','harbor-kiosk-session':'/usr/local/sbin/harbor-kiosk-session','harbour-package-update':'/usr/local/sbin/harbour-package-update','harbor-install.py':'/usr/local/sbin/harbor-install','installer-server.py':'/usr/local/sbin/harbor-installer-server','harbor-kernel-update':'/etc/initramfs/post-update.d/harbor-boot'}
def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})',value):raise ValueError('Use a numeric major.minor.patch release version.')
    return tuple(map(int,value.split('.')))
def sha(data):return hashlib.sha256(data).hexdigest()
def destination(name):
    parts=PurePosixPath(name)
    if parts.is_absolute() or '..' in parts.parts or '\\' in name or str(parts)!=name:raise ValueError('Invalid release file path.')
    if name.startswith('app/') and len(parts.parts)>1 and all(not p.startswith('.') for p in parts.parts):return 'app'
    if name.startswith('helpers/') and name[8:] in HELPERS:return HELPERS[name[8:]]
    raise ValueError('The release contains a file outside the allowed application/helper locations.')
def inspect_bundle(path,key,current,allow_same=False):
    if Path(path).stat().st_size>LIMIT:raise ValueError('The update bundle exceeds 64 MiB.')
    with zipfile.ZipFile(path) as archive:
        if sorted(archive.namelist())!=['manifest.json','manifest.sig','payload.tar.gz']:raise ValueError('Invalid or duplicate update bundle entries.')
        if any(i.file_size>LIMIT for i in archive.infolist()):raise ValueError('Oversized update archive entry.')
        raw=archive.read('manifest.json')
        if len(raw)>512*1024:raise ValueError('The update manifest is too large.')
        signature=archive.read('manifest.sig')
        if len(signature)!=64:raise ValueError('Invalid Ed25519 signature length.')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'manifest').write_bytes(raw);(root/'signature').write_bytes(signature)
            try:
                result=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(key),'-rawin','-in',str(root/'manifest'),'-sigfile',str(root/'signature')],capture_output=True)
                if result.returncode:raise ValueError('Signature verification failed. This release was not signed by the trusted Harbour key.')
            except FileNotFoundError:
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                try:
                    public=serialization.load_pem_public_key(Path(key).read_bytes())
                    if not isinstance(public,Ed25519PublicKey):raise ValueError('The trusted key is not Ed25519')
                    public.verify(signature,raw)
                except Exception as error:raise ValueError('Signature verification failed.') from error
        manifest=json.loads(raw)
        if manifest.get('format')!=1 or manifest.get('product')!='harbour' or manifest.get('architecture')!='amd64' or manifest.get('base')!='debian13':raise ValueError('This release does not support this appliance.')
        target=version(manifest.get('version'));installed=version(current);minimum=version(manifest.get('minimum_version'))
        if target<installed or target==installed and not allow_same:raise ValueError('Choose a newer release; use explicit rollback for an earlier version.')
        if installed<minimum:raise ValueError('Install an intermediate Harbour release before this update.')
        payload=archive.read('payload.tar.gz')
    if sha(payload)!=manifest.get('payload_sha256'):raise ValueError('The update payload checksum does not match the signed manifest.')
    records=manifest.get('files')
    if not isinstance(records,dict) or not 1<=len(records)<=2000:raise ValueError('Invalid release file manifest.')
    seen=set();total=0;application_version=None
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
        for member in archive:
            if not member.isfile() or member.name in seen:raise ValueError('Release payload must contain unique regular files only.')
            destination(member.name);seen.add(member.name);total+=member.size
            if member.size>32*1024**2 or total>128*1024**2 or len(seen)>2000:raise ValueError('The expanded release exceeds its size limits.')
            record=records.get(member.name)
            if not isinstance(record,dict) or record.get('mode') not in (0o644,0o755):raise ValueError('Invalid release file metadata.')
            content=archive.extractfile(member).read()
            if sha(content)!=record.get('sha256'):raise ValueError('A release file checksum does not match.')
            if member.name=='app/server.py':
                tree=ast.parse(content)
                for node in tree.body:
                    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets) and isinstance(node.value,ast.Constant):application_version=node.value.value
    if seen!=set(records) or application_version!=manifest['version'] or 'app/web/index.html' not in seen:raise ValueError('The release file list or application version is inconsistent.')
    return manifest,payload
def unpack_verified(manifest,payload,root):
    root=Path(root);root.mkdir(mode=0o700,parents=True,exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
        for member in archive:
            destination(member.name);target=root/member.name;target.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
            with target.open('xb') as output:output.write(archive.extractfile(member).read())
            target.chmod(manifest['files'][member.name]['mode'])
