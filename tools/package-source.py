"""Package shareable source and UI files without machine-local state."""
from pathlib import Path
import tarfile
import ast

root = Path(__file__).resolve().parents[1]
tree=ast.parse((root/'harbor/server.py').read_text(encoding='utf-8'))
release=next(n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in n.targets))


def source_filter(member):
    parts = Path(member.name).parts
    if '__pycache__' in parts or member.name.endswith('.pyc'):
        return None
    return member


with tarfile.open(root / ('dist/harbour-'+release+'-source.tar.gz'), 'w:gz') as archive:
    for name in ('.github','.gitignore','.gitattributes', 'LICENSE', 'README.md', 'harbor', 'os', 'tools', 'tests', 'docs'):
        archive.add(root / name, arcname=name, filter=source_filter)
    for name in ('harbour-'+release+'-amd64.iso.sha256','harbour-'+release+'-amd64.harbour-update.sha256'):
        if (root/'dist'/name).is_file():archive.add(root / 'dist' / name, arcname='dist/' + name)

with tarfile.open(root / 'dist/harbor-dark-desktop-ui.tar.gz', 'w:gz') as archive:
    for name in ('index.html', 'app.js','features.js','desktop.js','widgets.js','process.js','refinements.css','maintenance.js','maintenance.css','theme.js','experience.js','experience.css','wallpaper.svg','onboarding.js','install.js','install.html','desktop.css', 'style.css', 'favicon.svg'):
        archive.add(root / 'harbor/web' / name, arcname=name)

print('Source and dark desktop UI packaged.')
