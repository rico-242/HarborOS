"""Vendor an exact upstream official catalog snapshot; never execute upstream scripts."""
from pathlib import Path
import io
import json
import sys
import tarfile
import urllib.request

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / '.local/pylibs'))
import yaml
import copy
import re

class ComposeLoader(yaml.SafeLoader):
    pass
ComposeLoader.yaml_implicit_resolvers=copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for key,resolvers in ComposeLoader.yaml_implicit_resolvers.items():
    ComposeLoader.yaml_implicit_resolvers[key]=[(tag,rule) for tag,rule in resolvers if tag!='tag:yaml.org,2002:bool']
ComposeLoader.add_implicit_resolver('tag:yaml.org,2002:bool',re.compile(r'^(?:true|false|True|False|TRUE|FALSE)$'),list('tTfF'))

revision = (root / '.local/catalog-revision.txt').read_text().strip()
url = f'https://codeload.github.com/IceWhaleTech/CasaOS-AppStore/tar.gz/{revision}'
request = urllib.request.Request(url, headers={'User-Agent': 'HarborOS-build'})
data = urllib.request.urlopen(request, timeout=120).read()
output = root / 'harbor/catalog'
output.mkdir(exist_ok=True)
entries = []
with tarfile.open(fileobj=io.BytesIO(data)) as archive:
    for member in archive.getmembers():
        parts = member.name.split('/')
        if not member.isfile():
            continue
        if len(parts) == 2 and parts[-1] == 'LICENSE':
            (output / 'UPSTREAM-LICENSE').write_bytes(archive.extractfile(member).read())
        if len(parts) != 4 or parts[1] != 'Apps' or parts[-1] not in ('docker-compose.yml','docker-compose.yaml'):
            continue
        ident = parts[2].lower()
        if not __import__('re').fullmatch(r'[a-z0-9][a-z0-9_.-]{0,63}', ident):
            continue
        spec = yaml.load(archive.extractfile(member).read(),Loader=ComposeLoader)
        meta = spec.get('x-casaos', {})
        localized = lambda x: x.get('en_US', x.get('en_us', next(iter(x.values()), ''))) if isinstance(x, dict) else x or ''
        title = localized(meta.get('title')) or parts[2]
        icon_url=meta.get('icon','')
        icon_name=icon_url.split('/Apps/',1)[-1] if '/Apps/' in icon_url else ''
        icon_member=next((m for m in archive.getmembers() if m.isfile() and m.name.endswith('/Apps/'+icon_name)),None) if icon_name else None
        icon_path=''
        if icon_member and icon_member.size < 2*1024*1024 and Path(icon_name).suffix.lower() in ('.svg','.png','.jpg','.jpeg','.webp','.gif'):
            (output/'icons').mkdir(exist_ok=True)
            icon_path='icons/'+ident+Path(icon_name).suffix.lower()
            (output/icon_path).write_bytes(archive.extractfile(icon_member).read())
        entries.append({'id': ident, 'name': title, 'description': localized(meta.get('tagline')) or localized(meta.get('description'))[:260], 'detail':localized(meta.get('description')),
            'category': meta.get('category', 'Other'), 'architectures': meta.get('architectures', []),
            'icon': '/catalog/'+icon_path if icon_path else '', 'screenshots': meta.get('screenshot_link',[]),
            'port': str(meta.get('port_map','')), 'scheme': meta.get('scheme','http'), 'path': meta.get('index','/'),
            'developer': meta.get('developer',''), 'author': meta.get('author',''), 'website': meta.get('project_url',''),
            'main': meta.get('main',''), 'compose': spec})

assert len(entries) > 100, 'Unexpectedly small upstream catalog'
catalog = {'source': 'IceWhaleTech/CasaOS-AppStore', 'revision': revision, 'license': 'Apache-2.0',
           'apps': sorted(entries, key=lambda x: x['name'].casefold())}
(output / 'official.json').write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
(output / 'NOTICE').write_text('Official ZimaOS app definitions from IceWhaleTech/CasaOS-AppStore, Apache License 2.0.\n'
    f'Snapshot {revision}. Converted from YAML to JSON; Harbor supplies its own UI and Compose adapter.\n'
    'Application images, icons, and names belong to their respective projects.\n', encoding='utf-8')
print(f'Vendored {len(entries)} official app definitions at {revision}')
print('Examples:', ', '.join(x['name'] for x in catalog['apps'][:12]))
