"""Build a signed update; the private key is never included in the payload."""
import argparse,ast,hashlib,io,json,os,sys,tarfile,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'harbor'));sys.path.insert(0,str(root/'.local/pylibs'))
from release_bundle import HELPERS,version
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
parser=argparse.ArgumentParser();parser.add_argument('--key',required=True);parser.add_argument('--generate-key',action='store_true');parser.add_argument('--version',required=True);parser.add_argument('--minimum-version',default='0.3.1');parser.add_argument('--notes',default='Harbour release update');args=parser.parse_args();version(args.version);version(args.minimum_version)
key_path=Path(args.key)
if key_path.resolve().is_relative_to(root) and not key_path.resolve().is_relative_to(root/'.local'):raise SystemExit('Keep the private signing key outside published source directories, or under .local/signing.')
if args.generate_key:
    if key_path.exists():raise SystemExit('Refusing to overwrite an existing signing key')
    key_path.parent.mkdir(parents=True,exist_ok=True);key=Ed25519PrivateKey.generate();key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));key_path.chmod(0o600)
else:key=serialization.load_pem_private_key(key_path.read_bytes(),password=None)
if not isinstance(key,Ed25519PrivateKey):raise SystemExit('An Ed25519 signing key is required')
public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
public_path=root/'os/release-public.pem'
if public_path.exists() and public_path.read_bytes()!=public:raise SystemExit('The signing key does not match os/release-public.pem')
public_path.write_bytes(public)
tree=ast.parse((root/'harbor/server.py').read_text(encoding='utf-8'));actual=next(n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in n.targets))
if actual!=args.version:raise SystemExit('The bundle version must match harbor/server.py VERSION')
records={};buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
    files=[(p,'app/'+p.relative_to(root/'harbor').as_posix(),0o644) for p in sorted((root/'harbor').rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    files += [(root/'os'/name,'helpers/'+name,0o755) for name in HELPERS]
    for path,name,mode in files:
        data=path.read_bytes();info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode;info.mtime=0;archive.addfile(info,io.BytesIO(data));records[name]={'sha256':hashlib.sha256(data).hexdigest(),'mode':mode}
payload=buffer.getvalue();manifest={'format':1,'product':'harbour','version':args.version,'minimum_version':args.minimum_version,'architecture':'amd64','base':'debian13','requires_reboot':False,'notes':args.notes,'payload_sha256':hashlib.sha256(payload).hexdigest(),'files':records}
raw=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode();signature=key.sign(raw)
output=root/'dist'/f'harbour-{args.version}-amd64.harbour-update';output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as archive:
    archive.writestr('manifest.json',raw);archive.writestr('manifest.sig',signature);archive.writestr('payload.tar.gz',payload)
Path(str(output)+'.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+'\n',encoding='ascii',newline='\n')
print('Signed update built: '+str(output));print('Public key SHA-256: '+hashlib.sha256(public).hexdigest())
