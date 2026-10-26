"""Sign an immutable, tested GitHub ISO for recovery. Keep the key local."""
import argparse,base64,json,sys,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'harbor'),str(root/'.local/pylibs')]
from recovery import canonical
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
p=argparse.ArgumentParser();p.add_argument('--key',required=True);p.add_argument('--version',required=True);p.add_argument('--repository',default='rico-242/HarborOS');args=p.parse_args()
from release_bundle import version
version(args.version)
with urllib.request.urlopen('https://api.github.com/repos/'+args.repository+'/releases/tags/v'+args.version) as response:release=json.load(response)
assert not release['draft']
iso=next(a for a in release['assets'] if a['name']=='harbour-'+args.version+'-amd64.iso')
with urllib.request.urlopen('https://github.com/'+args.repository+'/releases/download/v'+args.version+'/iso-validation.json') as response:report=json.load(response)
assert report['version']==args.version and all(report['read_only_usb_boot'][mode]['installer_ready'] for mode in ('bios','uefi'))
assert iso['digest'].startswith('sha256:')
key=serialization.load_pem_private_key(Path(args.key).read_bytes(),password=None);assert isinstance(key,Ed25519PrivateKey)
assert key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)==(root/'os/release-public.pem').read_bytes()
manifest=dict(product='harbour-recovery',architecture='amd64',version=args.version,url=iso['browser_download_url'],size=iso['size'],sha256=iso['digest'][7:])
envelope=dict(manifest=manifest,signature=base64.b64encode(key.sign(canonical(manifest))).decode())
target=root/'dist/harbour-recovery.json';target.write_text(json.dumps(envelope,indent=2)+'\n',encoding='utf-8',newline='\n')
print('Signed recovery metadata:',target)
