"""Bundle unchanged featured artwork from the pinned, Apache-2.0 app catalog."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.request

root=Path(__file__).resolve().parents[1]
catalog=json.loads((root/'harbor/catalog/official.json').read_text())
prefix='https://cdn.jsdelivr.net/gh/IceWhaleTech/CasaOS-AppStore@main/'
records=[]
for ident in ('blinko','openclaw','weknora','openwebui','immich','archivebox','jellyfin'):
    app=next(a for a in catalog['apps'] if a['id']==ident)
    thumbnail=app['compose']['x-casaos']['thumbnail']
    if not thumbnail.startswith(prefix):raise ValueError('Unexpected catalog artwork source')
    relative=thumbnail.removeprefix(prefix)
    if '..' in PurePosixPath(relative).parts or not relative.startswith('Apps/') or not relative.endswith('/thumbnail.png'):
        raise ValueError('Unexpected artwork path')
    url='https://raw.githubusercontent.com/IceWhaleTech/CasaOS-AppStore/'+catalog['revision']+'/'+relative
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Harbour-catalog-artwork'}),timeout=30) as response:
        content=response.read(4*1024**2+1)
    if len(content)>4*1024**2 or not content.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Expected bounded PNG artwork')
    target=root/'harbor/catalog/icons'/('featured-'+ident+'.png')
    target.write_bytes(content)
    records.append({'id':ident,'file':target.name,'source':url,'sha256':hashlib.sha256(content).hexdigest()})
    print('Bundled '+ident+' featured artwork ('+str(len(content))+' bytes).')
(root/'harbor/catalog/featured-artwork.json').write_text(json.dumps({'revision':catalog['revision'],'license':'Apache-2.0','files':records},indent=2)+'\n',encoding='utf-8',newline='\n')
