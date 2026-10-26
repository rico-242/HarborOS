"""Read the one authoritative release version without importing the service."""
import ast,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
tree=ast.parse((root/'harbor/server.py').read_text(encoding='utf-8'))
values=[n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in n.targets) and isinstance(n.value,ast.Constant)]
if len(values)!=1 or not isinstance(values[0],str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',values[0]):raise SystemExit('Expected one numeric VERSION in harbor/server.py')
print(values[0])
