set -eu
python3 - <<'PY'
from pathlib import Path
root=Path('/mnt/harbor-zima-reference/usr/share/casaos/www')
for p in root.rglob('*'):
    if p.is_file() and any(x in p.name.lower() for x in ['wallpaper','background','default.jpg','default.png']):
        print(str(p.relative_to(root)),p.stat().st_size)
css=(root/'assets/index-yeNfqxRp.css').read_text()
import re
print('Most frequent neutral colors:',__import__('collections').Counter(re.findall(r'#[0-9a-fA-F]{6}',css)).most_common(12))
PY
